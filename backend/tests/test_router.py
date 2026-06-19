"""测试 router.route_query — 用 fake_provider 隔离 LLM 调用。

对应 specs/router.spec.md（暂未单独写 spec，行为由 router.py 内的 ROUTER_SCHEMA + system prompt 定义）。
"""

from __future__ import annotations


def test_route_query_returns_normalized_domain(fake_provider):
    fake_provider.structured_response = {
        "domain": "hr",
        "intent": "leave_inquiry",
        "confidence": 0.9,
        "reasoning": "user asks about annual leave",
        "needs_tools": True,
    }
    from kb_qa_agent.core.router import route_query
    result = route_query("我想休年假")
    assert result["domain"] == "hr"
    assert result["intent"] == "leave_inquiry"
    assert result["confidence"] == 0.9
    assert result["needs_tools"] is True


def test_route_query_normalizes_unknown_domain_to_general(fake_provider):
    """模型返回非法 domain 时应当 fallback 到 general，不抛错。"""
    fake_provider.structured_response = {
        "domain": "marketing",  # 不在 5 域里
        "intent": "?",
        "confidence": 0.5,
        "reasoning": "",
        "needs_tools": False,
    }
    from kb_qa_agent.core.router import route_query
    result = route_query("?")
    assert result["domain"] == "general"


def test_route_query_normalizes_uppercase_domain(fake_provider):
    fake_provider.structured_response = {
        "domain": "HR",
        "intent": "x",
        "confidence": 0.5,
        "reasoning": "",
        "needs_tools": False,
    }
    from kb_qa_agent.core.router import route_query
    result = route_query("?")
    assert result["domain"] == "hr"


def test_route_query_passes_history_to_provider(fake_provider):
    fake_provider.structured_response = {
        "domain": "hr",
        "intent": "x",
        "confidence": 0.5,
        "reasoning": "",
        "needs_tools": False,
    }
    history = [
        {"role": "user", "content": "我是 E001"},
        {"role": "assistant", "content": "好的"},
    ]
    from kb_qa_agent.core.router import route_query
    route_query("年假还剩几天？", conversation_history=history)
    # 核对 provider 看到了 history 中的内容
    structured_call = next(c for c in fake_provider.calls if c["method"] == "structured")
    msg_contents = " ".join(m.content for m in structured_call["messages"])
    assert "E001" in msg_contents


def test_route_query_truncates_long_history(fake_provider):
    """只保留最近 6 条；更早的不应在 prompt 里。"""
    fake_provider.structured_response = {
        "domain": "general",
        "intent": "x",
        "confidence": 0.5,
        "reasoning": "",
        "needs_tools": False,
    }
    history = [{"role": "user", "content": f"OLD-MSG-{i}"} for i in range(20)]
    history.append({"role": "user", "content": "RECENT-MSG"})
    from kb_qa_agent.core.router import route_query
    route_query("?", conversation_history=history)
    structured_call = next(c for c in fake_provider.calls if c["method"] == "structured")
    msg_contents = " ".join(m.content for m in structured_call["messages"])
    assert "RECENT-MSG" in msg_contents
    assert "OLD-MSG-0" not in msg_contents
