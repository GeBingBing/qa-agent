"""测试 flows/plan_gen.py — 计划生成三件套（RAG + Skill 选择 + DAG）。

策略：stub RAG / load_decision_cards / plan_with_retry 各路依赖，验证 generate_plan
对结果的拼装 + 对异常路径的兜底。
"""

from __future__ import annotations

from typing import Any

import pytest
from kb_qa_agent.core.rag import RetrievalHit


class _StubCard:
    def __init__(self, skill_id: str, domain: str = "hr"):
        self.skill_id = skill_id
        self.domain = domain
        self.trust_level = "trusted"


class _StubTrustGateResult:
    def __init__(self, cards: list[_StubCard], blocked: list[_StubCard] | None = None):
        self.passed = cards
        self.blocked = blocked or []


class _StubSelectResult(dict):
    """select_by_model 返回 dict，subclass 仅为类型友好。"""


@pytest.fixture
def stub_deps(monkeypatch):
    """把 plan_gen 的三个外部依赖全部 stub 成可控输入。"""
    # 1) plan_with_retry → 返回固定 Plan
    from kb_qa_agent.core import Plan
    from kb_qa_agent.flows import plan_gen as plan_gen_mod
    fake_plan = Plan(rationale="fake", nodes=[])

    plan_calls: list[dict[str, Any]] = []

    def fake_plan_with_retry(query, *, domain, available_tools, selected_skills, extra_context, max_retries):
        plan_calls.append({
            "query": query,
            "domain": domain,
            "available_tools": list(available_tools),
            "selected_skills": list(selected_skills),
            "extra_context": dict(extra_context),
            "max_retries": max_retries,
        })
        return fake_plan

    monkeypatch.setattr(plan_gen_mod, "plan_with_retry", fake_plan_with_retry)

    # 2) load_decision_cards → 4 张卡，2 hr + 1 finance + 1 general
    cards = [
        _StubCard("hr-policy-review", "hr"),
        _StubCard("hr-leave-flow", "hr"),
        _StubCard("finance-approval-check", "finance"),
        _StubCard("agently-request", "general"),
    ]

    def fake_load():
        return cards

    monkeypatch.setattr(plan_gen_mod, "load_decision_cards", fake_load)

    # 3) apply_trust_gate → 全过（trusted）
    def fake_trust(cards_arg):
        return _StubTrustGateResult(cards_arg)

    monkeypatch.setattr(plan_gen_mod, "apply_trust_gate", fake_trust)

    # 4) select_by_model → 选 hr-policy-review + hr-leave-flow
    def fake_select(query, candidates):
        ids = {c.skill_id for c in candidates}
        return _StubSelectResult(selected=[
            {"skill_id": "hr-policy-review"},
            {"skill_id": "hr-leave-flow"},
        ]) if ids else _StubSelectResult(selected=[])

    monkeypatch.setattr(plan_gen_mod, "select_by_model", fake_select)

    return {
        "plan_calls": plan_calls,
        "fake_plan": fake_plan,
        "cards": cards,
    }


def test_generate_plan_hr_domain_with_rag_hits(stub_deps, monkeypatch):
    """hr 域 + RAG 命中 → rag_hits 非空 + selected_skills 只含 hr 域。"""
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    class FakeRAG:
        def retrieve(self, query, *, top_k, where):
            return [
                RetrievalHit(text="hit1", metadata={"source": "a.md", "domain": "hr"}, score=0.1),
                RetrievalHit(text="hit2", metadata={"source": "b.md", "domain": "hr"}, score=0.2),
            ]

    result = plan_gen_mod.generate_plan(
        "年假流程",
        domain="hr",
        rag=FakeRAG(),
        use_rag=True,
        use_skills=True,
    )
    assert result["plan"] is stub_deps["fake_plan"]
    assert len(result["rag_hits"]) == 2
    assert {s["skill_id"] for s in result["selected_skills"]} == {"hr-policy-review", "hr-leave-flow"}
    assert result["blocked_skills"] == []
    # plan_with_retry 应被调用，且 available_tools 受 domain 过滤
    assert len(stub_deps["plan_calls"]) == 1
    pc = stub_deps["plan_calls"][0]
    assert pc["domain"] == "hr"
    assert pc["max_retries"] == 3
    # extra_context 应含 rag_chunks + selected_skills
    assert "rag_chunks" in pc["extra_context"]
    assert pc["selected_skills"] == ["hr-policy-review", "hr-leave-flow"]


def test_generate_plan_rag_failure_does_not_raise(stub_deps, monkeypatch):
    """RAG.retrieve 抛异常 → 不冒泡，写入 extra_context['rag_error']。"""
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    class BrokenRAG:
        def retrieve(self, query, *, top_k, where):
            raise ConnectionError("chroma unreachable")

    result = plan_gen_mod.generate_plan(
        "query",
        domain="hr",
        rag=BrokenRAG(),
        use_rag=True,
        use_skills=True,
    )
    assert result["rag_hits"] == []
    assert result["extra_context"].get("rag_error") == "chroma unreachable"


def test_generate_plan_skills_failure_does_not_raise(stub_deps, monkeypatch):
    """load_decision_cards 抛异常 → 不冒泡，写入 extra_context['skills_error']。"""
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    def boom():
        raise RuntimeError("skills down")

    monkeypatch.setattr(plan_gen_mod, "load_decision_cards", boom)
    result = plan_gen_mod.generate_plan(
        "q",
        domain="hr",
        rag=None,
        use_rag=False,
        use_skills=True,
    )
    assert result["selected_skills"] == []
    assert result["extra_context"].get("skills_error") == "skills down"


def test_generate_plan_general_domain_uses_all_tools(stub_deps, monkeypatch):
    """general 域 → available_tools 是 registry 全部（不过滤）。"""
    from kb_qa_agent.core.tool_registry import GLOBAL_REGISTRY
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    # 注册一些测试工具
    saved = dict(GLOBAL_REGISTRY._tools)
    GLOBAL_REGISTRY._tools.clear()
    GLOBAL_REGISTRY.register("t1", "t1", lambda: None, domain="hr")
    GLOBAL_REGISTRY.register("t2", "t2", lambda: None, domain="finance")
    GLOBAL_REGISTRY.register("t3", "t3", lambda: None, domain="general")
    try:
        plan_gen_mod.generate_plan(
            "q",
            domain="general",
            rag=None,
            use_rag=False,
            use_skills=False,
        )
    finally:
        GLOBAL_REGISTRY._tools.clear()
        GLOBAL_REGISTRY._tools.update(saved)

    pc = stub_deps["plan_calls"][0]
    assert set(pc["available_tools"]) == {"t1", "t2", "t3"}


def test_generate_plan_rag_disabled_skips_retrieve(stub_deps, monkeypatch):
    """use_rag=False → 不调 rag.retrieve。"""
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    class SpyRAG:
        called = False

        def retrieve(self, query, *, top_k, where):
            SpyRAG.called = True
            return []

    result = plan_gen_mod.generate_plan(
        "q",
        domain="hr",
        rag=SpyRAG(),
        use_rag=False,  # 关闭 RAG
        use_skills=False,
    )
    assert SpyRAG.called is False
    assert result["rag_hits"] == []


def test_generate_plan_skills_disabled(stub_deps, monkeypatch):
    """use_skills=False → 不调 load_decision_cards。"""
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    called = {"n": 0}

    def fake_load():
        called["n"] += 1
        return []

    monkeypatch.setattr(plan_gen_mod, "load_decision_cards", fake_load)
    result = plan_gen_mod.generate_plan(
        "q",
        domain="hr",
        rag=None,
        use_rag=False,
        use_skills=False,
    )
    assert called["n"] == 0
    assert result["selected_skills"] == []


def test_generate_plan_rag_skipped_for_general_domain(stub_deps):
    """domain='general' → 即使 use_rag=True 也不调 rag.retrieve。"""
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    class SpyRAG:
        called = False

        def retrieve(self, query, *, top_k, where):
            SpyRAG.called = True
            return []

    plan_gen_mod.generate_plan(
        "q",
        domain="general",
        rag=SpyRAG(),
        use_rag=True,
        use_skills=False,
    )
    assert SpyRAG.called is False


def test_generate_plan_no_rag_instance(stub_deps):
    """rag=None → 跳过 RAG，不抛。"""
    from kb_qa_agent.flows import plan_gen as plan_gen_mod

    result = plan_gen_mod.generate_plan(
        "q",
        domain="hr",
        rag=None,
        use_rag=True,
        use_skills=False,
    )
    assert result["rag_hits"] == []
