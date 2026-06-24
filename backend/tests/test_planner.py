"""测试 Planner — DAG 校验与拓扑排序。

对应 specs/planner.spec.md。重点：不依赖 LLM 的纯逻辑测试。
"""

from __future__ import annotations

import pytest
from kb_qa_agent.core.planner import (
    Plan,
    PlannerError,
    PlanNode,
    plan_dag,
    plan_with_retry,
    topological_order,
    validate_plan,
)

# ---------------------------------------------------------------------------
# 校验：合法 plan
# ---------------------------------------------------------------------------


def test_validate_simple_plan_passes():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="a", kind="tool", title="A"),
        PlanNode(id="b", kind="llm", title="B", depends_on=["a"]),
    ])
    validate_plan(plan)  # should not raise


def test_validate_single_node():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="only", kind="llm", title="Only"),
    ])
    validate_plan(plan)


def test_validate_diamond_dag():
    """A → B, A → C, B+C → D，标准菱形 DAG。"""
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="a", kind="tool", title="A"),
        PlanNode(id="b", kind="llm", title="B", depends_on=["a"]),
        PlanNode(id="c", kind="llm", title="C", depends_on=["a"]),
        PlanNode(id="d", kind="llm", title="D", depends_on=["b", "c"]),
    ])
    validate_plan(plan)


# ---------------------------------------------------------------------------
# 校验：错误 plan
# ---------------------------------------------------------------------------


def test_validate_duplicate_id_raises():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="dup", kind="tool", title="A"),
        PlanNode(id="dup", kind="llm", title="B"),
    ])
    with pytest.raises(PlannerError, match="duplicate"):
        validate_plan(plan)


def test_validate_unknown_dependency_raises():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="a", kind="tool", title="A", depends_on=["ghost"]),
    ])
    with pytest.raises(PlannerError, match="unknown node"):
        validate_plan(plan)


def test_validate_self_dependency_raises():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="a", kind="tool", title="A", depends_on=["a"]),
    ])
    with pytest.raises(PlannerError, match="depends on itself"):
        validate_plan(plan)


def test_validate_cycle_raises():
    """A → B → C → A 形成环。"""
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="a", kind="llm", title="A", depends_on=["c"]),
        PlanNode(id="b", kind="llm", title="B", depends_on=["a"]),
        PlanNode(id="c", kind="llm", title="C", depends_on=["b"]),
    ])
    with pytest.raises(PlannerError, match="cycle"):
        validate_plan(plan)


# ---------------------------------------------------------------------------
# 拓扑排序
# ---------------------------------------------------------------------------


def test_topological_order_chain():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="c", kind="llm", title="C", depends_on=["b"]),
        PlanNode(id="a", kind="tool", title="A"),
        PlanNode(id="b", kind="llm", title="B", depends_on=["a"]),
    ])
    order = topological_order(plan)
    ids = [n.id for n in order]
    # 不变量 I5：依赖在前，被依赖在后
    assert ids.index("a") < ids.index("b")
    assert ids.index("b") < ids.index("c")


def test_topological_order_diamond_preserves_dependency():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="a", kind="tool", title="A"),
        PlanNode(id="b", kind="llm", title="B", depends_on=["a"]),
        PlanNode(id="c", kind="llm", title="C", depends_on=["a"]),
        PlanNode(id="d", kind="llm", title="D", depends_on=["b", "c"]),
    ])
    order = topological_order(plan)
    ids = [n.id for n in order]
    assert ids.index("a") < ids.index("b")
    assert ids.index("a") < ids.index("c")
    assert ids.index("b") < ids.index("d")
    assert ids.index("c") < ids.index("d")


def test_topological_order_single_node():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="only", kind="llm", title="O"),
    ])
    assert [n.id for n in topological_order(plan)] == ["only"]


def test_topological_order_with_cycle_raises():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id="a", kind="llm", title="A", depends_on=["b"]),
        PlanNode(id="b", kind="llm", title="B", depends_on=["a"]),
    ])
    with pytest.raises(PlannerError, match="cycle"):
        topological_order(plan)


def test_topological_order_returns_all_nodes():
    plan = Plan(rationale="t", nodes=[
        PlanNode(id=f"n{i}", kind="tool", title=f"N{i}") for i in range(5)
    ])
    order = topological_order(plan)
    assert len(order) == 5
    assert {n.id for n in order} == {f"n{i}" for i in range(5)}


# ---------------------------------------------------------------------------
# plan_dag / plan_with_retry / _parse_plan（需要 mock TaskExecutor）
# ---------------------------------------------------------------------------


class _FakeExecutor:
    """模拟 TaskExecutor；按队列返回 raw dict 或抛异常。"""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = []
        self.provider_name = "fake"

    def run_structured(self, messages, *, schema, temperature=0.2, **kw):
        self.calls.append(messages)
        if not self._decisions:
            raise RuntimeError("no more decisions")
        nxt = self._decisions.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def test_plan_dag_success(monkeypatch):
    from kb_qa_agent.core import planner as planner_mod
    fake = _FakeExecutor([{"rationale": "r", "nodes": [
        {"id": "ans", "kind": "llm", "title": "answer"},
    ]}])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    p = plan_dag("q", domain="hr", available_tools=["t1"], selected_skills=["s1"],
                 extra_context={"k": "v"})
    assert p.rationale == "r"
    assert p.nodes[0].kind == "llm"
    # prompt 里应含工具 + skill + 上下文
    user_content = fake.calls[0][1].content
    assert "t1" in user_content
    assert "s1" in user_content
    assert "{'k': 'v'}" in user_content or "'k': 'v'" in user_content


def test_plan_dag_invalid_kind_raises(monkeypatch):
    from kb_qa_agent.core import planner as planner_mod
    fake = _FakeExecutor([{"rationale": "r", "nodes": [
        {"id": "a", "kind": "robot", "title": "A"},
    ]}])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    with pytest.raises(PlannerError, match="Invalid node kind"):
        plan_dag("q", domain="hr")


def test_parse_plan_defaults_kind_llm(monkeypatch):
    """节点缺 kind → 默认 llm。"""
    from kb_qa_agent.core import planner as planner_mod
    fake = _FakeExecutor([{"rationale": "r", "nodes": [
        {"id": "a", "title": "A"},  # 无 kind
    ]}])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    p = plan_dag("q", domain="hr")
    assert p.nodes[0].kind == "llm"


def test_parse_plan_missing_id_raises(monkeypatch):
    """节点缺 id → KeyError（解析失败快速失败）。"""
    from kb_qa_agent.core import planner as planner_mod
    fake = _FakeExecutor([{"rationale": "r", "nodes": [
        {"kind": "llm", "title": "A"},  # 缺 id
    ]}])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    with pytest.raises(KeyError):
        plan_dag("q", domain="hr")


def test_plan_with_retry_succeeds_first_try(monkeypatch):
    from kb_qa_agent.core import planner as planner_mod
    fake = _FakeExecutor([{"rationale": "ok", "nodes": [
        {"id": "a", "kind": "llm", "title": "A"},
    ]}])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    p = plan_with_retry("q", domain="hr", max_retries=3)
    assert p.rationale == "ok"
    assert len(fake.calls) == 1


def test_plan_with_retry_recovers_on_cycle(monkeypatch):
    """第一次 cycle 失败 → 把错误回灌 → 第二次 OK。"""
    from kb_qa_agent.core import planner as planner_mod
    bad = {"rationale": "r", "nodes": [
        {"id": "a", "kind": "llm", "title": "A", "depends_on": ["b"]},
        {"id": "b", "kind": "llm", "title": "B", "depends_on": ["a"]},
    ]}
    good = {"rationale": "fixed", "nodes": [
        {"id": "a", "kind": "llm", "title": "A"},
    ]}
    fake = _FakeExecutor([bad, good])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    p = plan_with_retry("q", domain="hr", max_retries=3)
    assert p.rationale == "fixed"
    assert len(fake.calls) == 2
    # 第二次调用的最后一条消息应含「重新规划」
    last_user = fake.calls[1][-1].content
    assert "未能通过校验" in last_user or "重新规划" in last_user


def test_plan_with_retry_recovers_on_parse_error(monkeypatch):
    """第一次 _parse_plan 抛 PlannerError（非法 kind）→ 重试 → OK。"""
    from kb_qa_agent.core import planner as planner_mod
    bad = {"rationale": "r", "nodes": [
        {"id": "a", "kind": "robot", "title": "A"},
    ]}
    good = {"rationale": "ok", "nodes": [
        {"id": "a", "kind": "llm", "title": "A"},
    ]}
    fake = _FakeExecutor([bad, good])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    p = plan_with_retry("q", domain="hr", max_retries=3)
    assert p.rationale == "ok"


def test_plan_with_retry_all_attempts_fail(monkeypatch):
    from kb_qa_agent.core import planner as planner_mod
    cycle = {"rationale": "r", "nodes": [
        {"id": "a", "kind": "llm", "title": "A", "depends_on": ["b"]},
        {"id": "b", "kind": "llm", "title": "B", "depends_on": ["a"]},
    ]}
    fake = _FakeExecutor([cycle, cycle, cycle])
    monkeypatch.setattr(planner_mod, "TaskExecutor", lambda *a, **kw: fake)
    with pytest.raises(PlannerError, match="Failed to produce"):
        plan_with_retry("q", domain="hr", max_retries=3)
    assert len(fake.calls) == 3
