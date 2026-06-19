"""测试 Planner — DAG 校验与拓扑排序。

对应 specs/planner.spec.md。重点：不依赖 LLM 的纯逻辑测试。
"""

from __future__ import annotations

import pytest

from kb_qa_agent.core.planner import (
    Plan,
    PlanNode,
    PlannerError,
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
