"""测试 ToolRegistry。

对应 specs/tool_registry.spec.md。
"""

from __future__ import annotations

import asyncio

import pytest
from kb_qa_agent.core.tool_registry import ToolRegistry, ToolSpec

# ---------------------------------------------------------------------------
# 注册 / 查询
# ---------------------------------------------------------------------------


def test_register_returns_tool_spec():
    reg = ToolRegistry()
    spec = reg.register("my_tool", "demo tool", lambda: 1)
    assert isinstance(spec, ToolSpec)
    assert spec.id == "my_tool"
    assert spec.desc == "demo tool"
    assert spec.side_effect_level == "read"
    assert spec.domain == ""
    assert spec.source == "builtin"


def test_register_duplicate_id_raises_value_error():
    reg = ToolRegistry()
    reg.register("dup", "first", lambda: 1)
    with pytest.raises(ValueError, match="already registered"):
        reg.register("dup", "second", lambda: 2)


def test_get_unknown_tool_raises_key_error():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_list_returns_in_registration_order():
    reg = ToolRegistry()
    reg.register("a", "a", lambda: None)
    reg.register("b", "b", lambda: None)
    reg.register("c", "c", lambda: None)
    assert reg.list_ids() == ["a", "b", "c"]


def test_empty_registry_returns_empty_list():
    reg = ToolRegistry()
    assert reg.list() == []
    assert reg.list_ids() == []
    assert reg.filter() == []


# ---------------------------------------------------------------------------
# 过滤
# ---------------------------------------------------------------------------


def test_filter_by_domain():
    reg = ToolRegistry()
    reg.register("h1", "hr tool", lambda: None, domain="hr")
    reg.register("f1", "finance tool", lambda: None, domain="finance")
    reg.register("h2", "hr tool 2", lambda: None, domain="hr")

    hr_tools = reg.filter(domain="hr")
    assert len(hr_tools) == 2
    assert {t.id for t in hr_tools} == {"h1", "h2"}


def test_filter_by_side_effect_max_read_excludes_write():
    reg = ToolRegistry()
    reg.register("r1", "read", lambda: None, side_effect_level="read")
    reg.register("w1", "write", lambda: None, side_effect_level="write")
    reg.register("e1", "external", lambda: None, side_effect_level="external")

    only_read = reg.filter(side_effect_max="read")
    assert len(only_read) == 1
    assert only_read[0].id == "r1"


def test_filter_by_side_effect_max_write_includes_read_and_write():
    reg = ToolRegistry()
    reg.register("r1", "read", lambda: None, side_effect_level="read")
    reg.register("w1", "write", lambda: None, side_effect_level="write")
    reg.register("e1", "external", lambda: None, side_effect_level="external")

    up_to_write = reg.filter(side_effect_max="write")
    ids = {t.id for t in up_to_write}
    assert ids == {"r1", "w1"}


def test_filter_no_match_returns_empty():
    reg = ToolRegistry()
    reg.register("h1", "hr", lambda: None, domain="hr")
    assert reg.filter(domain="legal") == []


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def test_execute_sync_function():
    reg = ToolRegistry()
    reg.register("add", "add two", lambda a, b: a + b)
    result = asyncio.run(reg.execute("add", a=2, b=3))
    assert result == 5


def test_execute_async_function():
    reg = ToolRegistry()

    async def echo(text: str) -> str:
        return f"echo: {text}"

    reg.register("echo", "echo", echo)
    result = asyncio.run(reg.execute("echo", text="hi"))
    assert result == "echo: hi"


def test_execute_unknown_tool_raises_key_error():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        asyncio.run(reg.execute("nope"))


def test_execute_propagates_tool_exception():
    reg = ToolRegistry()

    def boom():
        raise RuntimeError("boom")

    reg.register("boom", "boom", boom)
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(reg.execute("boom"))


# ---------------------------------------------------------------------------
# Prompt 渲染
# ---------------------------------------------------------------------------


def test_to_prompt_blocks_includes_metadata():
    reg = ToolRegistry()
    reg.register("t1", "demo tool", lambda: None, domain="hr", side_effect_level="write")
    text = reg.to_prompt_blocks()
    assert "t1" in text
    assert "demo tool" in text
    assert "hr" in text
    assert "write" in text


def test_to_prompt_blocks_with_subset_ids():
    reg = ToolRegistry()
    reg.register("a", "A", lambda: None)
    reg.register("b", "B", lambda: None)
    reg.register("c", "C", lambda: None)
    text = reg.to_prompt_blocks(["a", "c"])
    assert "id: a" in text
    assert "id: c" in text
    assert "id: b" not in text
