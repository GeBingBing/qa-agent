"""测试 providers/claude.py — Anthropic Claude/Opus 适配。

策略：mock `anthropic.Anthropic` / `AsyncAnthropic` 让 SDK 不出网，覆盖：
  - __init__ 默认 + env 覆盖
  - available() 依据 api_key
  - _split_system 把 system 消息拼成 string / 其余保持 list
  - chat() 解析 content blocks + usage
  - structured() 两次重试 + 第二次 raise
  - stream() 流式 chunk + 结束 usage
  - count_tokens() ascii / cjk 估算
  - price_per_1k() input / output
"""

from __future__ import annotations

from typing import Any

import pytest
from kb_qa_agent.providers.base import ChatMessage
from kb_qa_agent.providers.claude import ClaudeProvider

# ---------------------------------------------------------------------------
# __init__ / available
# ---------------------------------------------------------------------------


def test_init_defaults(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_MODEL", raising=False)
    p = ClaudeProvider()
    assert p.name == "opus"
    assert p.api_key == ""
    assert p.base_url == "https://api.anthropic.com"
    assert p.default_model == "claude-opus-4-8"
    assert p.input_price_per_1k == 15.0
    assert p.output_price_per_1k == 75.0


def test_init_picks_up_env(monkeypatch):
    """env vars 在构造时立刻读取。"""
    from kb_qa_agent.providers import claude as claude_mod
    monkeypatch.setattr(claude_mod, "_get_env", lambda key, default="": {
        "ANTHROPIC_API_KEY": "sk-test-abc",
        "ANTHROPIC_BASE_URL": "https://proxy.example.com",
        "ANTHROPIC_DEFAULT_MODEL": "claude-haiku-4-5",
    }.get(key, default))
    p = ClaudeProvider(api_key="x", base_url=None, default_model=None)
    # 注意：构造时如果显式传 None，self.default_model 会用 `or` 走 _get_env
    # 而 base_url 同理。但 api_key 显式传非空值，会跳过 _get_env。
    # 我们要验证的是：传 None 时确实走 env（间接覆盖 api_key 的行为不影响这一点）。
    assert p.base_url == "https://proxy.example.com"
    assert p.default_model == "claude-haiku-4-5"
    # api_key 走 _get_env 但显式传值覆盖：
    assert p.api_key == "x"


def test_available_true_when_key_set():
    p = ClaudeProvider(api_key="sk-test")
    assert p.available() is True


def test_available_false_when_no_key():
    p = ClaudeProvider(api_key="")
    assert p.available() is False


# ---------------------------------------------------------------------------
# _split_system
# ---------------------------------------------------------------------------


def test_split_system_no_system_message():
    system, rest = ClaudeProvider._split_system([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    assert system == ""
    assert len(rest) == 2


def test_split_system_single_system():
    system, rest = ClaudeProvider._split_system([
        {"role": "system", "content": "you are helpful"},
        {"role": "user", "content": "hi"},
    ])
    assert system == "you are helpful"
    assert rest == [{"role": "user", "content": "hi"}]


def test_split_system_multiple_system_concatenated():
    system, rest = ClaudeProvider._split_system([
        {"role": "system", "content": "be concise"},
        {"role": "system", "content": "use markdown"},
        {"role": "user", "content": "ok"},
    ])
    assert system == "be concise\n\nuse markdown"
    assert len(rest) == 1


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------


def test_count_tokens_empty_string():
    p = ClaudeProvider(api_key="x")
    assert p.count_tokens("") == 0


def test_count_tokens_ascii_only():
    p = ClaudeProvider(api_key="x")
    # 12 ascii chars → 12 / 4 = 3
    assert p.count_tokens("hello world!") == 3


def test_count_tokens_cjk_only():
    p = ClaudeProvider(api_key="x")
    # 6 CJK chars → 6 / 1.5 = 4
    assert p.count_tokens("你好世界你好") == 4


def test_count_tokens_mixed():
    p = ClaudeProvider(api_key="x")
    # "abc" (3 ascii → 3/4=0.75) + "你好" (2 CJK → 2/1.5=1.333) → int(2.083) = 2
    assert p.count_tokens("abc你好") == 2


# ---------------------------------------------------------------------------
# price_per_1k
# ---------------------------------------------------------------------------


def test_price_per_1k_input_output():
    p = ClaudeProvider(api_key="x", input_price_per_1k=3.0, output_price_per_1k=15.0)
    assert p.price_per_1k("any", "input") == 3.0
    assert p.price_per_1k("any", "output") == 15.0


# ---------------------------------------------------------------------------
# chat() — 走 mock Anthropic client
# ---------------------------------------------------------------------------


class _FakeUsage:
    def __init__(self, inp, out):
        self.input_tokens = inp
        self.output_tokens = out


class _FakeTextBlock:
    def __init__(self, text, type_="text"):
        self.text = text
        self.type = type_


class _FakeToolUseBlock(_FakeTextBlock):
    def __init__(self):
        self.type = "tool_use"


class _FakeMessage:
    def __init__(self, content_blocks, model="claude-opus-4-8", usage=None):
        self.content = content_blocks
        self.model = model
        self.usage = usage


class _FakeAnthropicMessages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeAnthropicClient:
    def __init__(self, response):
        self.messages = _FakeAnthropicMessages(response)


def test_chat_unavailable_raises():
    p = ClaudeProvider(api_key="")
    with pytest.raises(RuntimeError, match="not configured"):
        p.chat([ChatMessage(role="user", content="hi")])


def test_chat_concatenates_text_blocks(monkeypatch):
    p = ClaudeProvider(api_key="sk-test")
    resp = _FakeMessage([
        _FakeTextBlock("hello "),
        _FakeToolUseBlock(),  # 非 text 块应被跳过
        _FakeTextBlock("world"),
    ], usage=_FakeUsage(10, 5))
    p._client = _FakeAnthropicClient(resp)

    out = p.chat(
        [ChatMessage(role="system", content="be brief"),
         ChatMessage(role="user", content="hi")],
        temperature=0.5,
    )
    assert out.content == "hello world"
    assert out.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert out.model == "claude-opus-4-8"
    # messages.create 收到 system 单独拎出 + rest 是 user 列表
    call = p._client.messages.calls[0]
    assert call["system"] == "be brief"
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["temperature"] == 0.5
    assert call["model"] == "claude-opus-4-8"


def test_chat_handles_no_usage(monkeypatch):
    p = ClaudeProvider(api_key="sk-test")
    resp = _FakeMessage([_FakeTextBlock("hi")], usage=None)
    p._client = _FakeAnthropicClient(resp)
    out = p.chat([ChatMessage(role="user", content="hi")])
    assert out.content == "hi"
    assert out.usage == {}


def test_chat_uses_default_max_tokens(monkeypatch):
    p = ClaudeProvider(api_key="sk-test")
    resp = _FakeMessage([_FakeTextBlock("hi")])
    p._client = _FakeAnthropicClient(resp)
    p.chat([ChatMessage(role="user", content="hi")])
    call = p._client.messages.calls[0]
    assert call["max_tokens"] == 4096


# ---------------------------------------------------------------------------
# structured()
# ---------------------------------------------------------------------------


def test_structured_unavailable_raises():
    p = ClaudeProvider(api_key="")
    with pytest.raises(RuntimeError, match="not configured"):
        p.structured(
            [ChatMessage(role="user", content="x")],
            schema={"type": "object"},
        )


def test_structured_success_first_try(monkeypatch):
    p = ClaudeProvider(api_key="sk-test")

    class FakeResp:
        content = '{"answer": "ok"}'

    monkeypatch.setattr(p, "chat", lambda *a, **kw: FakeResp())
    # claude.py 内部 `from .structured import parse_json_response`，所以 patch structured 模块上的引用
    from kb_qa_agent.providers import structured as structured_mod

    monkeypatch.setattr(structured_mod, "parse_json_response", lambda text, schema: {"answer": "ok"})
    out = p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})
    assert out == {"answer": "ok"}


def test_structured_retry_then_succeed(monkeypatch):
    """第一次 parse 失败 → 重试；第二次成功 → 返回。"""
    p = ClaudeProvider(api_key="sk-test")
    calls = {"n": 0}

    class FakeResp:
        content = ""

    def fake_chat(*a, **kw):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(p, "chat", fake_chat)
    from kb_qa_agent.providers import structured as structured_mod

    responses = [ValueError("bad json"), {"answer": "retry-ok"}]

    def fake_parse(text, schema):
        v = responses.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(structured_mod, "parse_json_response", fake_parse)
    out = p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})
    assert out == {"answer": "retry-ok"}
    assert calls["n"] == 2


def test_structured_retry_exhausted_raises(monkeypatch):
    """两次 parse 都失败 → 第二次 raise。"""
    p = ClaudeProvider(api_key="sk-test")

    def fake_chat(*a, **kw):
        class R:
            content = ""
        return R()

    monkeypatch.setattr(p, "chat", fake_chat)
    from kb_qa_agent.providers import structured as structured_mod

    def fake_parse(text, schema):
        raise ValueError("always fail")

    monkeypatch.setattr(structured_mod, "parse_json_response", fake_parse)
    with pytest.raises(ValueError, match="always fail"):
        p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


class _FakeAsyncTextStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for c in self._chunks:
            yield c


class _FakeAsyncStream:
    """模拟 anthropic `client.messages.stream()` 上下文管理器。"""

    def __init__(self, chunks, final):
        self.text_stream = _FakeAsyncTextStream(chunks)
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_final_message(self):
        return self._final


class _FakeAsyncMessages:
    def __init__(self, chunks, final):
        self._chunks = chunks
        self._final = final
        self.calls: list[dict] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeAsyncStream(self._chunks, self._final)


class _FakeAsyncAnthropicClient:
    def __init__(self, chunks, final):
        self.messages = _FakeAsyncMessages(chunks, final)


@pytest.mark.asyncio
async def test_stream_unavailable_raises():
    p = ClaudeProvider(api_key="")
    with pytest.raises(RuntimeError, match="not configured"):
        async for _ in p.stream([ChatMessage(role="user", content="x")]):
            pass


@pytest.mark.asyncio
async def test_stream_yields_chunks_then_done(monkeypatch):
    p = ClaudeProvider(api_key="sk-test")
    chunks = ["hi ", "world"]
    final = _FakeMessage([], usage=_FakeUsage(8, 4))
    p._async_client = _FakeAsyncAnthropicClient(chunks, final)

    seen: list[Any] = []
    async for piece in p.stream(
        [ChatMessage(role="system", content="sys"),
         ChatMessage(role="user", content="hi")],
    ):
        seen.append(piece)

    # 前两个是 delta；最后一个是 done + usage
    assert seen[0].delta == "hi "
    assert seen[1].delta == "world"
    assert seen[2].delta == ""
    assert seen[2].done is True
    assert seen[2].usage == {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12}

    call = p._async_client.messages.calls[0]
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_stream_without_usage_emits_done_without_usage(monkeypatch):
    p = ClaudeProvider(api_key="sk-test")
    chunks = ["x"]
    final = _FakeMessage([], usage=None)
    p._async_client = _FakeAsyncAnthropicClient(chunks, final)
    seen = []
    async for piece in p.stream([ChatMessage(role="user", content="x")]):
        seen.append(piece)
    assert seen[-1].done is True
    assert seen[-1].usage == {}


# ---------------------------------------------------------------------------
# _ensure_sync / _ensure_async 用真实 anthropic SDK 走 lazy path
# ---------------------------------------------------------------------------


def test_ensure_sync_lazy_creates_client(monkeypatch):
    """首次访问 _client 时构造 Anthropic 实例；第二次复用。"""
    p = ClaudeProvider(api_key="sk-test")
    assert p._client is None
    c1 = p._ensure_sync()
    assert c1 is p._client
    c2 = p._ensure_sync()
    assert c2 is c1  # 不重复构造


def test_ensure_async_lazy_creates_client(monkeypatch):
    p = ClaudeProvider(api_key="sk-test")
    assert p._async_client is None
    c1 = p._ensure_async()
    assert c1 is p._async_client
    c2 = p._ensure_async()
    assert c2 is c1
