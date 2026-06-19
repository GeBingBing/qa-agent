"""测试流式过程中 <think> 块拆分为独立 SSE 事件。

期望：
  - `<think>...</think>` 内的字符通过 `thinking_delta` 推送
  - `</think>` 之后的字符通过 `answer_delta` 推送
  - 跨多个 stream chunk 的 `<think>` 标签也能正确分流（不会让标签字面量泄露）
  - final.final_answer 不含 <think>...</think>
"""

from __future__ import annotations

from typing import Any

import pytest

from kb_qa_agent.api.chat import split_thinking_stream


@pytest.mark.asyncio
async def test_split_thinking_clean_chunks():
    """单 chunk 同时包含 <think> 和正文。"""

    async def gen():
        for piece in ["<think>分析中</think>正文"]:
            yield piece

    events = []
    async for ev in split_thinking_stream(gen()):
        events.append(ev)

    types = [e["type"] for e in events]
    assert types == ["thinking", "answer", "final"]
    assert events[0]["delta"] == "分析中"
    assert events[1]["delta"] == "正文"
    assert events[2]["text"] == "正文"


@pytest.mark.asyncio
async def test_split_thinking_across_multiple_chunks():
    """`<think>` 标签横跨两个 chunk，仍要正确分流。"""

    async def gen():
        for piece in ["<thi", "nk>逐字思考", "继续</thi", "nk>最终"]:
            yield piece

    events = []
    async for ev in split_thinking_stream(gen()):
        events.append(ev)

    thinking_text = "".join(e["delta"] for e in events if e["type"] == "thinking")
    answer_text = "".join(e["delta"] for e in events if e["type"] == "answer")
    final = next(e for e in events if e["type"] == "final")

    assert thinking_text == "逐字思考继续"
    assert answer_text == "最终"
    assert final["text"] == "最终"
    # 输出绝不能包含原始标签字面量
    assert "<think" not in thinking_text and "</think" not in thinking_text
    assert "<think" not in answer_text and "</think" not in answer_text


@pytest.mark.asyncio
async def test_split_thinking_no_thinking_block():
    async def gen():
        yield "hello "
        yield "world"

    events = []
    async for ev in split_thinking_stream(gen()):
        events.append(ev)

    assert [e["type"] for e in events] == ["answer", "answer", "final"]
    assert events[-1]["text"] == "hello world"
