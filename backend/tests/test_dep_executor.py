"""测试 dep_executor.aexecute_plan / execute_plan。

P0-1：去掉 async 路径里的 asyncio.run。新增异步入口 aexecute_plan，
保证可在已经运行的事件循环中调用，而不再触发 RuntimeError。
"""

from __future__ import annotations

import asyncio

import pytest
from kb_qa_agent.core import GLOBAL_REGISTRY, Plan, PlanNode
from kb_qa_agent.flows.dep_executor import aexecute_plan, execute_plan

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_tool_plan(reset_registry):
    """注册一个返回 dict 的 mock tool，对应一个单 tool 节点的 Plan。"""

    async def fake_lookup(employee_id: str) -> dict:
        return {"employee_id": employee_id, "balance": 12}

    GLOBAL_REGISTRY.register(
        "fake_lookup",
        "look up balance",
        fake_lookup,
        domain="hr",
    )
    plan = Plan(
        rationale="single tool",
        nodes=[
            PlanNode(
                id="lookup",
                kind="tool",
                title="lookup balance",
                description='args: {"employee_id": "E001"}',
                binding="fake_lookup",
            ),
        ],
    )
    return plan


# ---------------------------------------------------------------------------
# aexecute_plan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aexecute_plan_runs_inside_event_loop(simple_tool_plan):
    """在已经运行的事件循环里直接 await，不应抛 RuntimeError。"""
    results = await aexecute_plan(simple_tool_plan, initial_inputs={"query": "q"})
    assert results["lookup"]["status"] == "ok"
    assert results["lookup"]["observation"] == {"employee_id": "E001", "balance": 12}
    assert results["__initial__"] == {"query": "q"}


@pytest.mark.asyncio
async def test_aexecute_plan_handles_sync_tool(reset_registry):
    """同步 tool 也要能正确执行（registry 内部走 to_thread）。"""

    def add(a: int, b: int) -> int:
        return a + b

    GLOBAL_REGISTRY.register("add", "add", add)
    plan = Plan(
        rationale="sync tool",
        nodes=[
            PlanNode(
                id="sum",
                kind="tool",
                title="add",
                description='args: {"a": 2, "b": 3}',
                binding="add",
            ),
        ],
    )
    results = await aexecute_plan(plan)
    assert results["sum"]["status"] == "ok"
    assert results["sum"]["observation"] == 5


@pytest.mark.asyncio
async def test_aexecute_plan_propagates_tool_error_into_node_result(reset_registry):
    """工具异常不应中断整个 plan，而是落入对应节点结果。"""

    def boom():
        raise RuntimeError("boom")

    GLOBAL_REGISTRY.register("boom", "boom", boom)
    plan = Plan(
        rationale="error tool",
        nodes=[PlanNode(id="x", kind="tool", title="boom", binding="boom")],
    )
    results = await aexecute_plan(plan)
    assert results["x"]["status"] == "error"
    assert "boom" in results["x"]["error"]


@pytest.mark.asyncio
async def test_aexecute_plan_executes_llm_node(fake_provider, reset_registry):
    """llm 节点用 TaskExecutor 拿到 content。"""
    fake_provider.chat_response_text = "hello world"
    plan = Plan(
        rationale="single llm",
        nodes=[PlanNode(id="ans", kind="llm", title="answer", binding="say hi")],
    )
    results = await aexecute_plan(plan)
    assert results["ans"]["status"] == "ok"
    assert results["ans"]["content"] == "hello world"


@pytest.mark.asyncio
async def test_aexecute_plan_human_node_marks_waiting(reset_registry):
    plan = Plan(
        rationale="human node",
        nodes=[PlanNode(id="ack", kind="human", title="manager approval")],
    )
    results = await aexecute_plan(plan)
    assert results["ack"]["status"] == "waiting_human"


@pytest.mark.asyncio
async def test_aexecute_plan_topological_order(reset_registry):
    """带依赖的 plan 必须按拓扑顺序执行，下游能看到上游结果。"""

    async def first():
        return {"v": 1}

    async def second(**kwargs):
        return {"got": kwargs}

    GLOBAL_REGISTRY.register("first", "first", first)
    GLOBAL_REGISTRY.register("second", "second", second)

    plan = Plan(
        rationale="dag",
        nodes=[
            PlanNode(id="a", kind="tool", title="a", binding="first"),
            PlanNode(
                id="b",
                kind="tool",
                title="b",
                binding="second",
                depends_on=["a"],
                description='args_from: a.observation',
            ),
        ],
    )
    results = await aexecute_plan(plan)
    assert results["a"]["status"] == "ok"
    assert results["b"]["status"] == "ok"
    assert results["b"]["observation"]["got"] == {"v": 1}


# ---------------------------------------------------------------------------
# execute_plan (sync wrapper) — keep backward compatibility
# ---------------------------------------------------------------------------


def test_execute_plan_still_works_in_pure_sync_context(reset_registry):
    """同步入口仍可工作（用于 eval CLI 等纯同步环境）。"""

    def add(a: int, b: int) -> int:
        return a + b

    GLOBAL_REGISTRY.register("add", "add", add)
    plan = Plan(
        rationale="sync wrapper",
        nodes=[
            PlanNode(
                id="sum",
                kind="tool",
                title="add",
                description='args: {"a": 2, "b": 3}',
                binding="add",
            ),
        ],
    )
    results = execute_plan(plan)
    assert results["sum"]["status"] == "ok"
    assert results["sum"]["observation"] == 5


def test_execute_plan_inside_running_loop_raises_clear_error(reset_registry):
    """在已经运行的 event loop 中调用同步 execute_plan 应给出明确提示，
    而不是吞掉为 status=error。"""

    async def fake_lookup() -> int:
        return 1

    GLOBAL_REGISTRY.register("fake_lookup", "lookup", fake_lookup)
    plan = Plan(
        rationale="trap",
        nodes=[PlanNode(id="x", kind="tool", title="lookup", binding="fake_lookup")],
    )

    async def call_in_loop():
        # 同步 execute_plan 在已运行的事件循环里应明确拒绝，而不是产生
        # asyncio.run 异常被吞为 status=error 的旧行为。
        with pytest.raises(RuntimeError, match="execute_plan"):
            execute_plan(plan)

    asyncio.run(call_in_loop())
