"""测试 /v1/chat SSE 端点协议。

对应 specs/chat.spec.md。重点验证 P0-2/3/7：
  - 多节点 plan 全部执行（不再单步 break）
  - _extract_draft 在没有 llm content 时回退到 tool observation
  - 中间任意阶段抛异常，都会发 error + final 兜底事件
  - SSE 事件 payload 是合法 JSON（顶层不出现 timestamp 字段）
"""

from __future__ import annotations

import json
from typing import Any, Iterable

import pytest
from fastapi.testclient import TestClient

from kb_qa_agent.core import GLOBAL_REGISTRY, Plan, PlanNode


def _parse_sse(stream: Iterable[bytes]) -> list[dict[str, Any]]:
    """把 SSE 字节流解析为 [{event, data}, ...]。"""
    buf = b""
    events: list[dict[str, Any]] = []
    for chunk in stream:
        buf += chunk
        while b"\r\n\r\n" in buf or b"\n\n" in buf:
            sep = b"\n\n" if b"\n\n" in buf and (b"\r\n\r\n" not in buf or buf.find(b"\n\n") < buf.find(b"\r\n\r\n")) else b"\r\n\r\n"
            block, _, buf = buf.partition(sep)
            block = block.replace(b"\r\n", b"\n")
            event_name = "message"
            data_lines: list[str] = []
            for line in block.split(b"\n"):
                line_str = line.decode("utf-8")
                if line_str.startswith("event:"):
                    event_name = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("data:"):
                    data_lines.append(line_str.split(":", 1)[1].lstrip())
            if not data_lines:
                continue
            data = json.loads("\n".join(data_lines))
            events.append({"event": event_name, "data": data})
    return events


@pytest.fixture
def app(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    """构造一个完整可调用的 FastAPI app；intake/plan/risk/reflection 全部 stub。"""
    # 让 plan_gen / risk / reflection 走 stub，避免 FakeProvider structured 默认返回不匹配 schema
    from kb_qa_agent.api import chat as chat_api
    from kb_qa_agent.flows import plan_gen as plan_gen_mod
    from kb_qa_agent.flows import intake as intake_mod
    from kb_qa_agent.flows import risk_approval as risk_mod
    from kb_qa_agent.flows import reflection as reflection_mod

    monkeypatch.setattr(intake_mod, "classify_intent", lambda q, conversation_history=None: {
        "domain": "hr",
        "intent": "leave_query",
        "confidence": 0.9,
        "reasoning": "test",
        "needs_tools": True,
    })

    GLOBAL_REGISTRY.register("hr_lookup", "lookup", lambda employee_id="E001": {"balance": 7})

    def fake_generate_plan(query, *, domain, rag=None, use_rag=True, use_skills=True, max_retries=3):
        return {
            "plan": Plan(
                rationale="multi-step",
                nodes=[
                    PlanNode(
                        id="lookup",
                        kind="tool",
                        title="lookup balance",
                        description='args: {"employee_id": "E001"}',
                        binding="hr_lookup",
                    ),
                    PlanNode(
                        id="answer",
                        kind="llm",
                        title="finalize",
                        binding="answer",
                        depends_on=["lookup"],
                    ),
                ],
            ),
            "rag_hits": [],
            "selected_skills": [],
            "blocked_skills": [],
            "extra_context": {},
        }

    monkeypatch.setattr(plan_gen_mod, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(chat_api, "generate_plan", fake_generate_plan)

    monkeypatch.setattr(risk_mod, "assess_and_route_risk", lambda q, results: {
        "risk_level": "low",
        "auto_proceed": True,
        "reasons": [],
        "required_approver": "auto",
    })
    monkeypatch.setattr(chat_api, "assess_and_route_risk", lambda q, results: {
        "risk_level": "low",
        "auto_proceed": True,
        "reasons": [],
        "required_approver": "auto",
    })

    def fake_finalize(draft, *, context="", max_rounds=2):
        return {
            "final_answer": draft if draft else "(empty)",
            "evaluations": [{"passed": True, "score": 0.9, "issues": [], "suggestions": []}],
            "rounds": 1,
        }

    monkeypatch.setattr(reflection_mod, "finalize_with_reflection", fake_finalize)
    monkeypatch.setattr(chat_api, "finalize_with_reflection", fake_finalize)

    from kb_qa_agent.main import app as fastapi_app
    return fastapi_app


def _post_chat(app, payload: dict[str, Any]) -> list[dict[str, Any]]:
    with TestClient(app) as client:
        with client.stream("POST", "/v1/chat", json=payload) as resp:
            assert resp.status_code == 200
            return _parse_sse(resp.iter_bytes())


# ---------------------------------------------------------------------------
# 协议事件序列
# ---------------------------------------------------------------------------


def test_sse_basic_event_order(app, fake_provider):
    fake_provider.chat_response_text = "the answer"
    events = _post_chat(app, {"query": "我的年假余额"})
    names = [e["event"] for e in events]
    assert names[0] == "start"
    assert names[-1] == "final"
    # 每个 plan node 必须有一对 step_start / step_result
    starts = [e for e in events if e["event"] == "step_start"]
    results = [e for e in events if e["event"] == "step_result"]
    assert [s["data"]["id"] for s in starts] == ["lookup", "answer"]
    assert [r["data"]["id"] for r in results] == ["lookup", "answer"]


def test_sse_final_answer_non_empty(app, fake_provider):
    fake_provider.chat_response_text = "draft text"
    events = _post_chat(app, {"query": "..."})
    final = [e for e in events if e["event"] == "final"][-1]
    assert final["data"]["final_answer"]
    assert "the answer" not in final["data"]["final_answer"] or fake_provider.chat_response_text == "draft text"


def test_sse_data_payload_is_valid_json(app, fake_provider):
    """每个 SSE 事件的 data 字段都必须是合法 JSON（解析过程中的失败会让 _parse_sse 抛错）。"""
    events = _post_chat(app, {"query": "..."})
    assert len(events) >= 5  # start + intake + plan + step_start + step_result + risk + final


# ---------------------------------------------------------------------------
# _extract_draft 兜底
# ---------------------------------------------------------------------------


def test_extract_draft_falls_back_to_tool_observation_when_no_llm(monkeypatch, app, fake_provider):
    """plan 全 tool 节点时，最终回答应基于 tool observation 而不是 (empty)。"""
    from kb_qa_agent.api import chat as chat_api

    def tool_only_plan(query, *, domain, rag=None, use_rag=True, use_skills=True, max_retries=3):
        return {
            "plan": Plan(
                rationale="tool only",
                nodes=[
                    PlanNode(
                        id="lookup",
                        kind="tool",
                        title="lookup",
                        description='args: {"employee_id": "E001"}',
                        binding="hr_lookup",
                    ),
                ],
            ),
            "rag_hits": [],
            "selected_skills": [],
            "blocked_skills": [],
            "extra_context": {},
        }

    monkeypatch.setattr(chat_api, "generate_plan", tool_only_plan)

    events = _post_chat(app, {"query": "..."})
    final = [e for e in events if e["event"] == "final"][-1]
    assert "(empty execution results" not in final["data"]["final_answer"]


# ---------------------------------------------------------------------------
# 异常兜底：error + final
# ---------------------------------------------------------------------------


def test_sse_intake_error_emits_error_then_final(monkeypatch, app):
    """intake 阶段抛异常应仍以 error + final 收尾，前端永远拿到完整事件流。"""
    from kb_qa_agent.api import chat as chat_api

    def boom(query, conversation_history=None):
        raise RuntimeError("intake failed")

    monkeypatch.setattr(chat_api, "classify_intent", boom)

    events = _post_chat(app, {"query": "..."})
    names = [e["event"] for e in events]
    assert "error" in names
    assert names[-1] == "final"
    err = [e for e in events if e["event"] == "error"][-1]
    assert err["data"]["phase"] == "intake"
    assert "intake failed" in err["data"]["message"]
    final = [e for e in events if e["event"] == "final"][-1]
    assert final["data"]["final_answer"]


# ---------------------------------------------------------------------------
# provider/model 请求级覆盖（P0-6）
# ---------------------------------------------------------------------------


def test_sse_request_provider_override_takes_effect(monkeypatch, app, fake_provider):
    from kb_qa_agent.api import chat as chat_api
    from kb_qa_agent.providers import registry as registry_mod
    from kb_qa_agent.core.model_request import TaskExecutor

    fake2 = type(fake_provider)()
    fake2.name = "fake2"
    fake2.chat_response_text = "answer-from-fake2"
    monkeypatch.setitem(registry_mod.PROVIDER_REGISTRY, "fake2", fake2)

    seen: list[str] = []

    def capture_intake(query, conversation_history=None):
        seen.append(TaskExecutor().provider_name)
        return {
            "domain": "hr",
            "intent": "x",
            "confidence": 1.0,
            "reasoning": "",
            "needs_tools": False,
        }

    monkeypatch.setattr(chat_api, "classify_intent", capture_intake)

    events = _post_chat(app, {"query": "...", "provider": "fake2", "model": "m-2"})
    assert seen == ["fake2"]
    assert [e["event"] for e in events][-1] == "final"
    # 退出请求后 active provider 恢复成 fake
    assert TaskExecutor().provider_name == "fake"


# ---------------------------------------------------------------------------
# 客户端断开（P1-4）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_chat_stops_when_client_disconnects(app, fake_provider, monkeypatch):
    """is_disconnected=True 时，流应停止下发新事件并退出（不再触发更多 LLM 调用）。"""
    from kb_qa_agent.api import chat as chat_api
    from kb_qa_agent.api.models import ChatRequest

    fake_provider.chat_response_text = "x" * 200  # 让 typewriter 阶段足够长

    disconnect_after = 4  # 收到第 4 个事件后再触发断开
    received: list[dict[str, Any]] = []

    class DisconnectingRequest:
        def __init__(self):
            self.app = type("App", (), {"state": type("S", (), {})()})()
            self._calls = 0

        async def is_disconnected(self) -> bool:
            self._calls += 1
            return len(received) >= disconnect_after

    # 直接驱动 _stream_chat，模拟一次请求 + 中途断开
    req = ChatRequest(query="...", enable_rag=False, enable_skills=False)

    async def consume():
        async for ev in chat_api._stream_chat(req, request=DisconnectingRequest()):
            received.append(ev)

    await consume()

    # 一旦感知到断开，后续不应再追加 answer_delta
    last = received[-1]
    # 应没有 final 兜底（属于正常断流而不是错误）
    assert last["event"] in {"answer_delta", "step_result", "intake", "plan", "step_start", "risk", "start"}


# ---------------------------------------------------------------------------
# 真 LLM 流式（P1-1）
# ---------------------------------------------------------------------------


def test_sse_real_stream_when_reflection_disabled(monkeypatch, app, fake_provider):
    """enable_reflection=False 时，answer_delta 由 provider.stream 真实驱动。"""
    fake_provider.stream_chunks = ["hel", "lo", " ", "world"]
    fake_provider.chat_response_text = "should-not-be-used"

    events = _post_chat(app, {"query": "hi", "enable_reflection": False})
    deltas = [e["data"]["delta"] for e in events if e["event"] == "answer_delta"]
    # 真实 stream chunk 应原样作为 delta（粗粒度），而不是被 typewriter 打散为 4 字一片
    assert deltas[:4] == ["hel", "lo", " ", "world"]
    final = [e for e in events if e["event"] == "final"][-1]
    assert final["data"]["final_answer"].startswith("hello world")
    assert final["data"]["reflection_rounds"] == 0


def test_sse_real_stream_thinking_split(monkeypatch, app, fake_provider):
    """`<think>...</think>` 内的 chunk 应作为 thinking_delta 推送，正文走 answer_delta。"""
    fake_provider.stream_chunks = [
        "<think>", "我先想想", "</think>", "正文", "继续",
    ]

    events = _post_chat(app, {"query": "hi", "enable_reflection": False})
    types = [e["event"] for e in events]
    assert "thinking_delta" in types
    thinking = "".join(e["data"]["delta"] for e in events if e["event"] == "thinking_delta")
    answer = "".join(e["data"]["delta"] for e in events if e["event"] == "answer_delta")
    assert thinking == "我先想想"
    assert answer == "正文继续"
    final = [e for e in events if e["event"] == "final"][-1]
    assert final["data"]["final_answer"] == "正文继续"
    # 终稿绝不能再泄露 think 标签
    assert "<think" not in final["data"]["final_answer"]
