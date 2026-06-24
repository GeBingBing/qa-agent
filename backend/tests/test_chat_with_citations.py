"""测试 P4-A3 + A-4：RAG 命中进入答案 + sources 事件。

期望：
  - api/chat.py 在 retrieval 后发 sources 事件
  - 事件 payload 含 id / source / heading_path / score / snippet
  - 注入到 finalize / real_stream prompt
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from kb_qa_agent.core.rag import RetrievalHit


@pytest.fixture
def app(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    """构造 app；stub plan_gen 让其返回固定 rag_hits。"""
    from kb_qa_agent.api import chat as chat_api
    from kb_qa_agent.core import Plan, PlanNode
    from kb_qa_agent.flows import (
        intake as intake_mod,
    )
    from kb_qa_agent.flows import (
        plan_gen as plan_gen_mod,
    )
    from kb_qa_agent.flows import (
        reflection as reflection_mod,
    )
    from kb_qa_agent.flows import (
        risk_approval as risk_mod,
    )
    from kb_qa_agent.main import app

    monkeypatch.setattr(intake_mod, "classify_intent", lambda q, conversation_history=None: {
        "domain": "hr",
        "intent": "leave_query",
        "confidence": 0.9,
        "reasoning": "x",
        "needs_tools": True,
    })

    fake_hits = [
        RetrievalHit(
            text="年假需提前 3 天申请，由直属经理审批，HR BP 复核。",
            metadata={"source": "leave_policy.md", "heading_path": "年假/申请流程", "domain": "hr"},
            score=0.12,
        ),
        RetrievalHit(
            text="病假超过 2 个工作日必须附医疗单。",
            metadata={"source": "sick_leave_policy.md", "heading_path": "病假/申请流程", "domain": "hr"},
            score=0.34,
        ),
    ]

    def fake_generate_plan(query, *, domain, rag=None, use_rag=True, use_skills=True, max_retries=3):
        return {
            "plan": Plan(
                rationale="answer",
                nodes=[PlanNode(id="ans", kind="llm", title="answer", binding="b")],
            ),
            "rag_hits": fake_hits,
            "selected_skills": [],
            "blocked_skills": [],
            "extra_context": {},
        }

    monkeypatch.setattr(plan_gen_mod, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(chat_api, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(risk_mod, "assess_and_route_risk", lambda q, r: {
        "risk_level": "low", "auto_proceed": True, "reasons": [], "required_approver": "auto",
    })
    monkeypatch.setattr(chat_api, "assess_and_route_risk", lambda q, r: {
        "risk_level": "low", "auto_proceed": True, "reasons": [], "required_approver": "auto",
    })
    monkeypatch.setattr(reflection_mod, "finalize_with_reflection", lambda draft, **_: {
        "final_answer": draft, "evaluations": [], "rounds": 0,
    })
    monkeypatch.setattr(chat_api, "finalize_with_reflection", lambda draft, **_: {
        "final_answer": draft, "evaluations": [], "rounds": 0,
    })
    return app


def _parse_sse(resp):
    """把 starlette TestClient 的 SSE 响应解析为 events 列表。"""
    import json

    raw = b""
    for chunk in resp.iter_bytes():
        raw += chunk
    text = raw.replace(b"\r\n", b"\n").decode("utf-8", errors="replace")
    out: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            line_s = line.strip()
            if line_s.startswith("event:"):
                event = line_s.split(":", 1)[1].strip()
            elif line_s.startswith("data:"):
                data_lines.append(line_s.split(":", 1)[1].lstrip())
        if data_lines:
            try:
                out.append({"event": event, "data": json.loads("\n".join(data_lines))})
            except Exception:  # noqa: BLE001
                pass
    return out


def test_sources_event_emitted_with_rag_hits(app):
    with TestClient(app) as client:
        with client.stream("POST", "/v1/chat", json={"query": "年假流程", "enable_reflection": False}) as resp:
            events = _parse_sse(resp)
    names = [e["event"] for e in events]
    assert "sources" in names
    sources = next(e for e in events if e["event"] == "sources")
    assert len(sources["data"]) == 2
    by_id = {s["id"]: s for s in sources["data"]}
    assert by_id[1]["source"] == "leave_policy.md"
    assert by_id[1]["heading_path"] == "年假/申请流程"
    assert "提前 3 天" in by_id[1]["snippet"]
    assert by_id[2]["source"] == "sick_leave_policy.md"


def test_rag_hits_inject_into_real_stream_prompt(app, fake_provider):
    """_real_stream_answer 在传给 provider 的 prompt 中包含 [i] 角标 + source 列表。

    fake provider 不解析 prompt，所以验证的是**prompt 构造**而非答案输出。
    """
    with TestClient(app) as client:
        with client.stream("POST", "/v1/chat", json={
            "query": "年假流程", "enable_reflection": False, "enable_rag": True,
        }) as resp:
            for _ in resp.iter_bytes():
                pass

    # 找到发往 active provider 的 stream 调用
    stream_calls = [c for c in fake_provider.calls if c["method"] == "stream"]
    assert stream_calls, "expected at least one provider.stream call"
    messages = stream_calls[-1]["messages"]
    assert len(messages) == 2
    system_msg, user_msg = messages[0], messages[1]
    assert system_msg.role == "system"
    assert user_msg.role == "user"

    system_prompt = system_msg.content
    user_prompt = user_msg.content

    # system prompt 明确要求角标规则
    assert "[1] [2]" in system_prompt or "[i]" in system_prompt
    assert "## 参考资料" in system_prompt

    # user prompt 含政策片段 + 角标 + source
    assert "## 政策片段" in user_prompt
    assert "[1]" in user_prompt
    assert "[2]" in user_prompt
    assert "leave_policy.md" in user_prompt
    assert "sick_leave_policy.md" in user_prompt


def test_sources_event_after_plan_before_streaming(app):
    """sources 事件在 plan 之后、第一个 answer_delta 之前。"""
    with TestClient(app) as client:
        with client.stream("POST", "/v1/chat", json={"query": "年假流程", "enable_reflection": False}) as resp:
            events = _parse_sse(resp)
    names = [e["event"] for e in events]
    plan_idx = names.index("plan")
    sources_idx = names.index("sources")
    first_delta_idx = next(i for i, n in enumerate(names) if n == "answer_delta")
    assert plan_idx < sources_idx < first_delta_idx


def test_sources_event_deduped_by_source():
    """如果 plan_gen 给了两个同 source 的 hits，sources 事件应该按 source 去重。"""
    # 注：去重策略放在 _build_sources_event()，测试其纯函数
    from kb_qa_agent.api.chat import _build_sources_event

    hits = [
        RetrievalHit(text="A段", metadata={"source": "x.md", "heading_path": "h1"}, score=0.1),
        RetrievalHit(text="B段", metadata={"source": "x.md", "heading_path": "h2"}, score=0.2),
    ]
    sources = _build_sources_event(hits)
    # 两个 hits 同 source 时保留 1 条（取 score 最低）
    assert len(sources) == 1
    assert sources[0]["id"] == 1
    assert sources[0]["snippet"] == "A段"
