"""api/chat.py — SSE 流式聊天端点。

  - 用 sse-starlette 把事件推到前端
  - 协议：specs/chat.spec.md（事件序列 / 不变量 / 错误模式）
  - error 事件 + final 兜底：异常发生时仍保证前端拿到完整事件流
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from ..core import RAG
from ..core.model_request import TaskExecutor, request_provider
from ..domains import bootstrap as bootstrap_domains
from ..flows import (
    aexecute_plan,
    assess_and_route_risk,
    classify_intent,
    finalize_with_reflection,
    generate_plan,
)
from ..observability import metrics as metrics_mod
from ..observability import tracer
from .models import ChatRequest
from .security import require_api_token

router = APIRouter(prefix="/v1", tags=["chat"])

TYPEWRITER_CHUNK_SIZE = 4
TYPEWRITER_DELAY_SECONDS = 0.015
MAX_SNIPPET_CHARS = 240
MAX_RAG_HITS_INTO_PROMPT = 4


def _build_sources_event(hits: list) -> list[dict[str, Any]]:
    """从 RetrievalHit 列表构造 sources 事件 payload。

    - 按 source 去重（保留 score 最低 / 最相关那条）
    - snippet 截到 MAX_SNIPPET_CHARS 字
    - id 从 1 开始递增
    """
    by_source: dict[str, dict[str, Any]] = {}
    for h in hits:
        src = h.metadata.get("source", "?")
        if src in by_source and by_source[src]["score"] <= h.score:
            continue
        by_source[src] = {
            "source": src,
            "heading_path": h.metadata.get("heading_path", ""),
            "score": round(float(h.score), 4),
            "snippet": h.text[:MAX_SNIPPET_CHARS],
        }
    sources = sorted(by_source.values(), key=lambda s: s["score"])
    for i, s in enumerate(sources, start=1):
        s["id"] = i
    return sources


def _format_rag_for_prompt(sources: list[dict[str, Any]]) -> str:
    """把 sources 渲染成可注入 prompt 的块（每条带 [i] 角标号）。"""
    if not sources:
        return "（无政策片段）"
    parts: list[str] = []
    for s in sources:
        heading = s.get("heading_path") or ""
        header = f"[{s['id']}] {s['source']}"
        if heading:
            header += f"#{heading}"
        parts.append(f"{header}\n{s['snippet']}")
    return "\n\n".join(parts)

# 启动时把 4 域工具注册到 GLOBAL_REGISTRY
_ = bootstrap_domains()


def _now() -> float:
    return time.time()


def _sse_event(event: str, data: dict[str, Any]) -> dict[str, str]:
    """构造 sse-starlette 可序列化的事件。"""
    return {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}


async def _typewriter_events(text: str) -> AsyncIterator[dict[str, str]]:
    """把已经生成完的回答拆成小片段，驱动前端打字机式渲染（用于反思后路径）。"""
    for index in range(0, len(text), TYPEWRITER_CHUNK_SIZE):
        yield _sse_event(
            "answer_delta",
            {"delta": text[index:index + TYPEWRITER_CHUNK_SIZE], "timestamp": _now()},
        )
        await asyncio.sleep(TYPEWRITER_DELAY_SECONDS)


async def _real_stream_answer(
    draft: str,
    *,
    intake: dict[str, Any],
    execution_results: dict[str, Any],
    risk: dict[str, Any],
    request: Request | None,
    rag_hits: list | None = None,
):
    """真 LLM 流式：基于上游 draft + 执行结果，让 active provider 增量产出 final answer。

    把模型输出按 `<think>...</think>` 拆成 thinking_delta / answer_delta 两条信道，
    最后再发一个 ``{"type": "final", "text": ...}`` 让调用方汇总。

    rag_hits 注入：系统 prompt 强制要求 [1] [2] 角标 + 段尾「## 参考资料」段。
    """
    from ..providers import ChatMessage  # noqa: WPS433 — 内部依赖按需导入

    sources = _build_sources_event(rag_hits or [])
    rag_block = _format_rag_for_prompt(sources)

    context_summary = json.dumps({
        "intake": intake,
        "execution": execution_results,
        "risk": risk,
    }, ensure_ascii=False, default=str)[:4000]
    system_prompt = (
        "你是企业知识库问答助手。基于已收集的上下文与初稿，"
        "生成一份高质量、结构化的最终回答。回答要简洁、准确、有可执行性。"
        "如果下方提供了「政策片段」，必须**严格依据**它们回答；"
        "在正文里用 [1] [2] 角标对应片段，"
        "并在最后追加「## 参考资料」段，列出 [i] source#heading。"
        "如果你需要展示思考过程，可以包在 <think>...</think> 中；"
        "最终回答放在 </think> 之后。"
    )
    user_prompt = (
        f"## 初稿\n{draft}\n\n"
        f"## 政策片段（用于引用，角标必须严格对应）\n{rag_block}\n\n"
        f"## 上下文（路由 / 执行 / 风险）\n{context_summary}\n\n"
        "请输出最终回答。"
    )

    executor = TaskExecutor()

    async def chunk_source():
        async for chunk in executor.astream_text([
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ], temperature=0.4):
            if request is not None and await _is_client_disconnected(request):
                return
            delta = getattr(chunk, "delta", "")
            if delta:
                yield delta

    async for piece in split_thinking_stream(chunk_source()):
        yield piece


async def _is_client_disconnected(request: Request | None) -> bool:
    if request is None:
        return False
    try:
        return await request.is_disconnected()
    except Exception:  # noqa: BLE001
        return False


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


async def split_thinking_stream(source):
    """把一个增量字符串流拆成 thinking / answer / final 事件。

    - 处于 `<think>...</think>` 之间的字符走 `thinking`
    - 其余字符走 `answer`
    - 跨多个 chunk 的标签会被缓冲到完整的开/闭标签后再决定归类
    - 流结束时发一次 `final`，文本是去掉所有 think 块后的最终回答

    Yields:
      {"type": "thinking", "delta": str}
      {"type": "answer", "delta": str}
      {"type": "final", "text": str}
    """
    buffer = ""
    in_thinking = False
    answer_chars: list[str] = []

    def flush(target_kind: str, text: str):
        if target_kind == "answer":
            answer_chars.append(text)
        return {"type": target_kind, "delta": text}

    async for piece in source:
        if not piece:
            continue
        buffer += piece
        # 反复扫描，每次只处理到第一个不完整的标签前
        while buffer:
            target_tag = _THINK_CLOSE if in_thinking else _THINK_OPEN
            idx = buffer.find(target_tag)
            if idx >= 0:
                if idx > 0:
                    chunk_text = buffer[:idx]
                    yield flush("thinking" if in_thinking else "answer", chunk_text)
                buffer = buffer[idx + len(target_tag):]
                in_thinking = not in_thinking
                continue
            # 没找到完整的目标标签 — 看末尾是不是部分匹配，需要继续等下一段
            partial = _partial_tag_suffix(buffer, target_tag)
            if partial:
                head = buffer[:-partial]
                if head:
                    yield flush("thinking" if in_thinking else "answer", head)
                buffer = buffer[-partial:]
                break
            # 末尾不是任何标签前缀 — 全部下发
            yield flush("thinking" if in_thinking else "answer", buffer)
            buffer = ""

    if buffer:
        # 流结束时缓冲里还有内容（说明从未匹配到目标标签）
        yield flush("thinking" if in_thinking else "answer", buffer)

    yield {"type": "final", "text": "".join(answer_chars).strip()}


def _partial_tag_suffix(buffer: str, tag: str) -> int:
    """返回 buffer 末尾与 tag 前缀匹配的最长长度（用于跨 chunk 缓冲）。"""
    max_len = min(len(tag) - 1, len(buffer))
    for length in range(max_len, 0, -1):
        if buffer.endswith(tag[:length]):
            return length
    return 0


def _extract_draft(results: dict[str, Any]) -> str:
    """从执行结果里挑出最近的可读内容当 draft。

    优先级：最后一个 llm content > 最后一个非空 tool observation > 空字符串。
    """
    for nid in reversed(list(results.keys())):
        if nid == "__initial__":
            continue
        node_result = results[nid]
        if not isinstance(node_result, dict):
            continue
        if node_result.get("content"):
            return str(node_result["content"])
    for nid in reversed(list(results.keys())):
        if nid == "__initial__":
            continue
        node_result = results[nid]
        if not isinstance(node_result, dict):
            continue
        obs = node_result.get("observation")
        if obs is None:
            continue
        if isinstance(obs, str):
            return obs
        return json.dumps(obs, ensure_ascii=False, default=str)
    return ""


def _blocked_answer(risk: dict[str, Any], execution_results: dict[str, Any]) -> str:
    return (
        "⚠️ 本回答被风险评估标记为 HIGH，需要法务/财务/合规负责人审批后才能发出。\n"
        f"评估理由：{', '.join(risk.get('reasons', []))}\n"
        f"建议审批人：{risk.get('required_approver', '?')}\n\n"
        "已收集的中间信息：\n"
        + json.dumps(execution_results, ensure_ascii=False, indent=2, default=str)[:1500]
    )


@contextlib.contextmanager
def _no_op_context():
    yield


async def _stream_chat(
    req: ChatRequest,
    *,
    shared_rag: RAG | None = None,
    request: Request | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """端到端 SSE 流。每完成一个 sub-flow 推一个事件；任何阶段抛异常都走 error+final 兜底。"""
    yield _sse_event("start", {"query": req.query, "ts": _now()})

    request_started = time.monotonic()
    metric_status = "ok"
    metric_provider = req.provider or os.environ.get("KB_QA_ACTIVE_PROVIDER", "deepseek")

    phase = "intake"
    domain = "general"
    plan_bundle: dict[str, Any] | None = None
    execution_results: dict[str, Any] = {}
    risk: dict[str, Any] = {
        "risk_level": "low",
        "auto_proceed": True,
        "reasons": [],
        "required_approver": "auto",
    }

    try:
        override = (
            request_provider(req.provider, model=req.model)
            if req.provider
            else _no_op_context()
        )
        with override, tracer.span("chat_request", attrs={"query": req.query[:200]}) as root:
            # Step 1: 路由
            phase = "intake"
            with tracer.span("intake", parent=root.span_id):
                intake = classify_intent(req.query, conversation_history=req.conversation_history)
            yield _sse_event("intake", {**intake, "timestamp": _now()})
            domain = intake.get("domain", "general")
            if await _is_client_disconnected(request):
                return

            # Step 2: RAG + Skills + Plan
            phase = "plan"
            with tracer.span("plan_gen", parent=root.span_id, attrs={"domain": domain}):
                rag = (shared_rag if shared_rag is not None else RAG()) if req.enable_rag else None
                plan_bundle = generate_plan(
                    req.query,
                    domain=domain,
                    rag=rag,
                    use_rag=req.enable_rag,
                    use_skills=req.enable_skills,
                )
            yield _sse_event("plan", {
                "rationale": plan_bundle["plan"].rationale,
                "nodes": [n.__dict__ for n in plan_bundle["plan"].nodes],
                "rag_hits_count": len(plan_bundle["rag_hits"]),
                "selected_skills": plan_bundle["selected_skills"],
                "blocked_skills": plan_bundle["blocked_skills"],
                "timestamp": _now(),
            })

            # Step 2.5: sources 事件（让前端在思考阶段就能渲染来源 chip）
            rag_hits = plan_bundle.get("rag_hits") or []
            if rag_hits:
                yield _sse_event("sources", _build_sources_event(rag_hits))
            if await _is_client_disconnected(request):
                return

            # Step 3: 执行 DAG（每个节点一对 step_start/step_result）
            phase = "execute"
            for node in plan_bundle["plan"].nodes:
                yield _sse_event("step_start", {
                    "id": node.id,
                    "kind": node.kind,
                    "title": node.title,
                    "timestamp": _now(),
                })
            with tracer.span("execute_plan", parent=root.span_id, attrs={"nodes": len(plan_bundle["plan"].nodes)}):
                execution_results = await aexecute_plan(
                    plan_bundle["plan"],
                    initial_inputs={"query": req.query, "domain": domain},
                )
            for node in plan_bundle["plan"].nodes:
                node_result = execution_results.get(node.id, {})
                yield _sse_event("step_result", {
                    "id": node.id,
                    "kind": node.kind,
                    "status": node_result.get("status", "unknown"),
                    "content": node_result.get("content"),
                    "observation": node_result.get("observation"),
                    "error": node_result.get("error"),
                    "timestamp": _now(),
                })
            if await _is_client_disconnected(request):
                return

            # Step 4: 风险评估
            phase = "risk"
            with tracer.span("risk_assessment", parent=root.span_id):
                risk = assess_and_route_risk(req.query, execution_results)
            yield _sse_event("risk", {**risk, "timestamp": _now()})
            if await _is_client_disconnected(request):
                return

            # Step 5: 反思 + 最终回答
            phase = "finalize"
            if risk["auto_proceed"] or risk["risk_level"] != "high":
                draft = _extract_draft(execution_results) or "(no upstream content)"
                rag_hits = plan_bundle.get("rag_hits") or []
                if req.enable_reflection:
                    with tracer.span("reflection_finalize", parent=root.span_id):
                        reflection = finalize_with_reflection(
                            draft,
                            context=json.dumps({
                                "intake": intake,
                                "execution": execution_results,
                                "risk": risk,
                                "rag_hits": [
                                    {"source": h.metadata.get("source"),
                                     "heading_path": h.metadata.get("heading_path"),
                                     "snippet": h.text[:MAX_SNIPPET_CHARS]}
                                    for h in rag_hits[:MAX_RAG_HITS_INTO_PROMPT]
                                ],
                            }, ensure_ascii=False, default=str)[:4000],
                            max_rounds=2,
                        )
                    final_answer = reflection["final_answer"] or draft
                    async for event in _typewriter_events(final_answer):
                        if await _is_client_disconnected(request):
                            return
                        yield event
                    yield _sse_event("final", {
                        "final_answer": final_answer,
                        "reflection_rounds": reflection["rounds"],
                        "evaluations": reflection["evaluations"],
                        "risk_level": risk["risk_level"],
                        "domain": domain,
                        "timestamp": _now(),
                    })
                else:
                    # 真流式：直接用 provider.stream() 推送增量
                    final_answer = ""
                    with tracer.span("real_stream_finalize", parent=root.span_id):
                        async for piece in _real_stream_answer(
                            draft,
                            intake=intake,
                            execution_results=execution_results,
                            risk=risk,
                            request=request,
                            rag_hits=rag_hits,
                        ):
                            kind = piece["type"]
                            if kind == "thinking":
                                yield _sse_event("thinking_delta", {
                                    "delta": piece["delta"],
                                    "timestamp": _now(),
                                })
                            elif kind == "answer":
                                yield _sse_event("answer_delta", {
                                    "delta": piece["delta"],
                                    "timestamp": _now(),
                                })
                            else:
                                final_answer = piece["text"]
                    if not final_answer:
                        final_answer = draft
                    yield _sse_event("final", {
                        "final_answer": final_answer,
                        "reflection_rounds": 0,
                        "evaluations": [],
                        "risk_level": risk["risk_level"],
                        "domain": domain,
                        "timestamp": _now(),
                    })
            else:
                final_answer = _blocked_answer(risk, execution_results)
                async for event in _typewriter_events(final_answer):
                    if await _is_client_disconnected(request):
                        return
                    yield event
                yield _sse_event("final", {
                    "final_answer": final_answer,
                    "blocked_by_risk": True,
                    "risk_level": risk["risk_level"],
                    "domain": domain,
                    "timestamp": _now(),
                })
    except Exception as exc:  # noqa: BLE001
        metric_status = "error"
        yield _sse_event("error", {
            "code": type(exc).__name__,
            "message": str(exc),
            "phase": phase,
            "timestamp": _now(),
        })
        fallback = (
            f"⚠️ 处理过程中出现错误（阶段：{phase}）：{exc}\n\n"
            "请稍后重试，或调整问题后再次提问。"
        )
        yield _sse_event("final", {
            "final_answer": fallback,
            "error": True,
            "phase": phase,
            "risk_level": risk.get("risk_level", "low"),
            "domain": domain,
            "timestamp": _now(),
        })
    finally:
        metrics_mod.record_chat(metric_status, metric_provider, time.monotonic() - request_started)


@router.post("/chat", dependencies=[Depends(require_api_token)])
async def chat(req: ChatRequest, request: Request):
    """SSE 端点。前端通过 fetch + ReadableStream 解析。"""
    shared_rag: RAG | None = getattr(request.app.state, "rag", None)
    return EventSourceResponse(_stream_chat(req, shared_rag=shared_rag, request=request))
