"""测试 P1-3：RAG 单例资源复用。

期望：
  - lifespan 启动时把 RAG 实例放到 app.state.rag
  - api/chat 优先复用 app.state.rag，避免每请求重建（embedding 模型加载昂贵）
  - 没有 app.state 时 fallback 到 RAG()，保证测试/CLI 仍可工作
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _parse_sse(stream):
    import json
    buf = b""
    out: list[dict[str, Any]] = []
    for chunk in stream:
        buf += chunk
        while b"\n\n" in buf or b"\r\n\r\n" in buf:
            sep = b"\n\n" if b"\n\n" in buf and (b"\r\n\r\n" not in buf or buf.find(b"\n\n") < buf.find(b"\r\n\r\n")) else b"\r\n\r\n"
            block, _, buf = buf.partition(sep)
            block = block.replace(b"\r\n", b"\n")
            event = "message"
            data_lines: list[str] = []
            for line in block.split(b"\n"):
                line_str = line.decode("utf-8")
                if line_str.startswith("event:"):
                    event = line_str.split(":", 1)[1].strip()
                elif line_str.startswith("data:"):
                    data_lines.append(line_str.split(":", 1)[1].lstrip())
            if not data_lines:
                continue
            out.append({"event": event, "data": json.loads("\n".join(data_lines))})
    return out


def test_rag_instance_lives_on_app_state(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    """app.state.rag 应在 lifespan 启动后存在；类型为 RAG。"""
    from kb_qa_agent.core.rag import RAG
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        client.get("/health")
        assert hasattr(app.state, "rag")
        assert isinstance(app.state.rag, RAG)


def test_chat_reuses_app_state_rag(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    """两次 /v1/chat 请求应共享同一个 RAG 实例（不重建）。"""
    from kb_qa_agent.api import chat as chat_api
    from kb_qa_agent.core import Plan, PlanNode
    from kb_qa_agent.flows import (
        intake as intake_mod,
    )
    from kb_qa_agent.main import app

    monkeypatch.setattr(intake_mod, "classify_intent", lambda q, conversation_history=None: {
        "domain": "general",
        "intent": "x",
        "confidence": 1.0,
        "reasoning": "",
        "needs_tools": False,
    })

    seen_rags: list[Any] = []

    def fake_generate_plan(query, *, domain, rag=None, use_rag=True, use_skills=True, max_retries=3):
        seen_rags.append(rag)
        return {
            "plan": Plan(
                rationale="r",
                nodes=[PlanNode(id="ans", kind="llm", title="answer", binding="hi")],
            ),
            "rag_hits": [],
            "selected_skills": [],
            "blocked_skills": [],
            "extra_context": {},
        }

    monkeypatch.setattr(chat_api, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(chat_api, "assess_and_route_risk", lambda q, r: {
        "risk_level": "low", "auto_proceed": True, "reasons": [], "required_approver": "auto",
    })
    monkeypatch.setattr(chat_api, "finalize_with_reflection", lambda draft, **_: {
        "final_answer": "ok", "evaluations": [], "rounds": 0,
    })

    with TestClient(app) as client:
        for _ in range(2):
            with client.stream("POST", "/v1/chat", json={"query": "x", "enable_rag": True}) as resp:
                _parse_sse(resp.iter_bytes())

    # 两次请求拿到的应是同一个 RAG 实例
    assert len(seen_rags) == 2
    assert seen_rags[0] is not None
    assert seen_rags[0] is seen_rags[1]
    assert seen_rags[0] is app.state.rag


def test_chat_disable_rag_passes_none(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    """enable_rag=False 时不应传 RAG 实例进 plan_gen。"""
    from kb_qa_agent.api import chat as chat_api
    from kb_qa_agent.core import Plan, PlanNode
    from kb_qa_agent.flows import intake as intake_mod
    from kb_qa_agent.main import app

    monkeypatch.setattr(intake_mod, "classify_intent", lambda q, conversation_history=None: {
        "domain": "general", "intent": "x", "confidence": 1.0, "reasoning": "", "needs_tools": False,
    })

    captured: list[Any] = []

    def fake_generate_plan(query, *, domain, rag=None, use_rag=True, use_skills=True, max_retries=3):
        captured.append(rag)
        return {
            "plan": Plan(rationale="", nodes=[PlanNode(id="ans", kind="llm", title="t", binding="b")]),
            "rag_hits": [], "selected_skills": [], "blocked_skills": [], "extra_context": {},
        }

    monkeypatch.setattr(chat_api, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(chat_api, "assess_and_route_risk", lambda q, r: {
        "risk_level": "low", "auto_proceed": True, "reasons": [], "required_approver": "auto",
    })
    monkeypatch.setattr(chat_api, "finalize_with_reflection", lambda draft, **_: {
        "final_answer": "ok", "evaluations": [], "rounds": 0,
    })

    with TestClient(app) as client:
        with client.stream("POST", "/v1/chat", json={"query": "x", "enable_rag": False}) as resp:
            _parse_sse(resp.iter_bytes())

    assert captured == [None]
