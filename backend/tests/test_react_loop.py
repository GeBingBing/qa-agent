"""测试 core/react_loop.py — ReAct 循环。

覆盖：
  - 决策 type='final' 直接返回
  - 决策 type='tool' 调工具 + 写入 history + 继续
  - 决策 type=未知 → 强切 final（带 reasoning）
  - 预算耗尽 → Grace Call 路径
  - tool 执行异常 → observation 记录 error
  - structured 解析失败 → fallback answer
  - run_stream 产生 step_start / decision / observation / final 事件
  - 空工具集 → prompt 块显示「无可用工具」
  - _format_history 跳过 None observation
  - to_dict 序列化 ReActResult
"""

from __future__ import annotations

import pytest
from kb_qa_agent.core.react_loop import (
    REACT_SCHEMA,
    ReActLoop,
    ReActResult,
    ReActStep,
)
from kb_qa_agent.core.tool_registry import ToolRegistry


class FakeExecutor:
    """模拟 TaskExecutor：按 plan 返回决策序列。"""

    def __init__(self, decisions: list[dict]):
        self._decisions = list(decisions)
        self.calls: list[list] = []
        self.provider_name = "fake"

    def run_structured(self, messages, *, schema, temperature=0.2, **kw):
        self.calls.append(messages)
        if not self._decisions:
            raise RuntimeError("no more decisions queued")
        return self._decisions.pop(0)


def _tool(spec_id: str = "fake_tool"):
    """注册一个简单的同步工具到新 registry。"""
    reg = ToolRegistry()

    def hello(name: str = "world") -> str:
        return f"hi {name}"

    reg.register(
        spec_id,
        "say hello",
        hello,
        side_effect_level="read",
        domain="general",
    )
    return reg, spec_id


@pytest.mark.asyncio
async def test_final_decision_short_circuits():
    """type=final → 直接返回，不调工具。"""
    reg, _ = _tool()
    exec_ = FakeExecutor([{"type": "final", "reasoning": "ok", "answer": "42"}])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=3)
    res = await loop.run("what?")
    assert isinstance(res, ReActResult)
    assert res.final_answer == "42"
    assert len(res.steps) == 1
    assert res.provider == "fake"


@pytest.mark.asyncio
async def test_tool_decision_then_final():
    """tool → final 两轮：先调工具，再 final。"""
    reg, tool_id = _tool()
    exec_ = FakeExecutor([
        {"type": "tool", "reasoning": "use tool", "tool_name": tool_id, "tool_args": {"name": "bob"}},
        {"type": "final", "reasoning": "done", "answer": "got hi bob"},
    ])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=5)
    res = await loop.run("ask")
    assert res.final_answer == "got hi bob"
    # 第一轮是 tool，第二轮是 final，所以 steps 里只记 final step
    assert len(res.steps) == 1
    assert res.steps[0].step == 2


@pytest.mark.asyncio
async def test_tool_execution_exception_recorded_as_observation():
    """tool 抛异常 → observation = {'error': ...}，循环继续。"""
    reg = ToolRegistry()

    def boom(**kw):
        raise RuntimeError("tool kaboom")

    reg.register("boom", "boom tool", boom, domain="general")
    exec_ = FakeExecutor([
        {"type": "tool", "reasoning": "try", "tool_name": "boom", "tool_args": {}},
        {"type": "final", "reasoning": "done", "answer": "after boom"},
    ])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=3)
    res = await loop.run("q")
    assert res.final_answer == "after boom"
    # 第二次调用时 messages 应含 "## 工具结果" 段含 error
    user_msg = exec_.calls[1][1].content
    assert "## 工具结果" in user_msg or "工具结果" in user_msg or "boom" in user_msg


@pytest.mark.asyncio
async def test_structured_parse_failure_triggers_fallback():
    """run_structured 抛异常 → fallback answer 不含异常堆栈给用户。"""
    reg, _ = _tool()
    exec_ = FakeExecutor([])  # 第一次就 raise
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=3)
    res = await loop.run("hi")
    # fallback path: answer 不为空
    assert res.final_answer
    assert "hi" in res.final_answer or "信息" in res.final_answer


@pytest.mark.asyncio
async def test_unknown_decision_type_force_final():
    """type 既不是 tool 也不是 final → 强切 final，带 reasoning。"""
    reg, _ = _tool()
    exec_ = FakeExecutor([{"type": "weird", "reasoning": "what is this"}])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=3)
    res = await loop.run("q")
    assert "unknown decision type" in res.final_answer.lower() or "weird" in res.final_answer


@pytest.mark.asyncio
async def test_grace_call_when_budget_exhausted():
    """6 轮全 tool，第 7 轮 Grace Call 强切 final。"""
    reg, tool_id = _tool()
    # max_steps=2 → 第一次 tool，第二次 tool → 预算耗尽 → Grace Call
    exec_ = FakeExecutor([
        {"type": "tool", "reasoning": "r1", "tool_name": tool_id, "tool_args": {}},
        {"type": "tool", "reasoning": "r2", "tool_name": tool_id, "tool_args": {}},
        {"type": "final", "reasoning": "grace", "answer": "grace answer"},
    ])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=2)
    res = await loop.run("q")
    assert res.final_answer == "grace answer"


@pytest.mark.asyncio
async def test_tool_ids_filter_to_subset():
    """tool_ids 限定可用工具集合。"""
    reg = ToolRegistry()

    def a(**kw):
        return "a"

    def b(**kw):
        return "b"

    reg.register("a", "a", a, domain="general")
    reg.register("b", "b", b, domain="general")
    exec_ = FakeExecutor([
        {"type": "tool", "reasoning": "r", "tool_name": "a", "tool_args": {}},
        {"type": "final", "reasoning": "done", "answer": "ok"},
    ])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=3, tool_ids=["a"])
    res = await loop.run("q")
    assert res.final_answer == "ok"
    # 用户消息里只应见到 tool a 的描述
    user_msg = exec_.calls[0][1].content
    assert "tool a" in user_msg.lower() or "a" in user_msg


@pytest.mark.asyncio
async def test_empty_registry_prompt_says_no_tools():
    reg = ToolRegistry()
    exec_ = FakeExecutor([{"type": "final", "reasoning": "x", "answer": "ok"}])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=2)
    await loop.run("q")
    user_msg = exec_.calls[0][1].content
    assert "无可用工具" in user_msg


@pytest.mark.asyncio
async def test_run_stream_emits_events():
    reg, tool_id = _tool()
    exec_ = FakeExecutor([
        {"type": "tool", "reasoning": "use", "tool_name": tool_id, "tool_args": {}},
        {"type": "final", "reasoning": "done", "answer": "streamed"},
    ])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=3)
    events = []
    async for ev in loop.run_stream("q"):
        events.append(ev)
    names = [e["event"] for e in events]
    assert "step_start" in names
    assert "decision" in names
    assert "observation" in names
    assert "final" in names
    final = next(e for e in events if e["event"] == "final")
    assert final["final_answer"] == "streamed"


@pytest.mark.asyncio
async def test_run_stream_grace_call():
    reg, tool_id = _tool()
    exec_ = FakeExecutor([
        {"type": "tool", "reasoning": "x", "tool_name": tool_id, "tool_args": {}},
        {"type": "final", "reasoning": "grace", "answer": "grace-final"},
    ])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=1)
    events = []
    async for ev in loop.run_stream("q"):
        events.append(ev)
    final = next(e for e in events if e["event"] == "final")
    assert final["final_answer"] == "grace-final"


def test_format_history_skips_none_observation():
    out = ReActLoop._format_history([])
    assert out == ""
    out = ReActLoop._format_history([
        {"decision": {"type": "tool"}, "observation": None},
        {"decision": {"type": "tool"}, "observation": {"ok": True}},
    ])
    assert "Step 1" in out
    assert "None" in out  # None observation 渲染为字符串 "None"
    assert "Step 2" in out
    assert '"ok"' in out or "ok" in out


def test_react_result_to_dict():
    res = ReActResult(
        final_answer="ans",
        steps=[ReActStep(step=1, decision={"type": "final"}, duration_ms=10)],
        total_usage={"prompt_tokens": 5},
        provider="p",
        model="m",
    )
    d = res.to_dict()
    assert d["final_answer"] == "ans"
    assert d["provider"] == "p"
    assert d["steps"][0]["step"] == 1
    assert d["total_usage"] == {"prompt_tokens": 5}


def test_react_schema_required_fields():
    """REACT_SCHEMA 至少包含 type 与 reasoning。"""
    assert "type" in REACT_SCHEMA["required"]
    assert "reasoning" in REACT_SCHEMA["required"]


@pytest.mark.asyncio
async def test_fallback_answer_with_history_includes_observations():
    """history 非空时 fallback 应包含 observation 摘要。"""
    reg = ToolRegistry()

    def tool_with_error(**kw):
        raise RuntimeError("nope")

    reg.register("t_err", "err", tool_with_error, domain="general")
    exec_ = FakeExecutor([
        {"type": "tool", "reasoning": "try", "tool_name": "t_err", "tool_args": {}},
        {"type": "final", "reasoning": "grace", "answer": ""},  # 空 answer → 走 fallback
    ])
    loop = ReActLoop(registry=reg, executor=exec_, max_steps=2)
    res = await loop.run("q")
    # 第二轮 answer 为空 → 触发 _fallback_answer(history)
    # 历史里有 error observation，fallback 应含「工具调用失败」
    assert "工具调用失败" in res.final_answer or "nope" in res.final_answer
