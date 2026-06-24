"""测试 providers/openai_compat.py — OpenAI 兼容 Provider 适配。

策略：mock openai.OpenAI / AsyncOpenAI 客户端，覆盖：
  - __init__ 默认 + env 注入
  - available() 双向校验
  - chat: 完整 message + usage + 无 usage 路径
  - structured: response_format 注入 + 重试 + 重试用尽
  - supports_response_formats: 6 家白名单 + 自托管不在白名单
  - stream: 流式 chunk + done + usage
  - count_tokens: 空 / ascii / cjk / 混合
  - price_per_1k
  - 客户端懒加载（sync / async 各一次）
"""

from __future__ import annotations

import pytest
from kb_qa_agent.providers.base import ChatMessage
from kb_qa_agent.providers.openai_compat import OpenAICompatProvider

# ---------------------------------------------------------------------------
# env key helpers
# ---------------------------------------------------------------------------


def test_env_key_for_dispatch():
    """_env_key_for → api_key_env(provider_name)"""
    assert OpenAICompatProvider._env_key_for("deepseek") == "DEEPSEEK_API_KEY"
    assert OpenAICompatProvider._env_key_for("dashscope") == "DASHSCOPE_API_KEY"


def test_env_base_for_dispatch():
    assert OpenAICompatProvider._env_base_for("kimi").endswith("BASE_URL")


def test_env_model_for_dispatch():
    out = OpenAICompatProvider._env_model_for("minimax")
    assert "MINIMAX" in out and "MODEL" in out


# ---------------------------------------------------------------------------
# __init__ / available
# ---------------------------------------------------------------------------


def test_init_empty_provider_unavailable():
    p = OpenAICompatProvider(name="custom")
    assert p.name == "custom"
    assert p.available() is False


def test_init_picks_up_env(monkeypatch):
    monkeypatch.setattr(
        "kb_qa_agent.providers.openai_compat.api_key_env",
        lambda name: "DEEPSEEK_API_KEY",
    )
    monkeypatch.setattr(
        "kb_qa_agent.providers.openai_compat.base_url_env",
        lambda name: "DEEPSEEK_BASE_URL",
    )
    monkeypatch.setattr(
        "kb_qa_agent.providers.openai_compat.default_model_env",
        lambda name: "DEEPSEEK_MODEL",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    p = OpenAICompatProvider(name="deepseek")
    assert p.api_key == "sk-test"
    assert p.base_url == "https://api.deepseek.com"
    assert p.default_model == "deepseek-chat"
    assert p.available() is True


def test_available_requires_both_key_and_base():
    """available() 双向校验：key 与 base_url 都必须非空。"""
    p = OpenAICompatProvider(name="x")
    p.api_key = "k"
    p.base_url = ""
    assert p.available() is False
    p.api_key = ""
    p.base_url = "u"
    assert p.available() is False
    p.api_key = "k"
    p.base_url = "u"
    assert p.available() is True


# ---------------------------------------------------------------------------
# supports_response_formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_name", [
    "openai", "deepseek", "dashscope", "glm", "kimi", "minimax",
])
def test_supports_response_formats_whitelist(provider_name):
    p = OpenAICompatProvider(name=provider_name)
    assert p.supports_response_formats() == {"json_object"}


def test_supports_response_formats_unknown_provider_empty():
    p = OpenAICompatProvider(name="custom-vllm")
    assert p.supports_response_formats() == set()


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


class _FakeUsage:
    def __init__(self, p, c, t):
        self.prompt_tokens = p
        self.completion_tokens = c
        self.total_tokens = t


class _FakeChoice:
    def __init__(self, content):
        self.message = type("Msg", (), {"content": content})()


class _FakeChatResponse:
    def __init__(self, content, model="m", usage=None):
        self.choices = [_FakeChoice(content)]
        self.model = model
        self.usage = usage


class _FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return self.response


class _FakeChatNamespace:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeSyncClient:
    def __init__(self, response):
        self.chat = _FakeChatNamespace(response)


def test_chat_unavailable_raises():
    p = OpenAICompatProvider(name="custom")
    with pytest.raises(RuntimeError, match="not configured"):
        p.chat([ChatMessage(role="user", content="hi")])


def test_chat_with_usage(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x", default_model="deepseek-chat")
    resp = _FakeChatResponse(
        "hello",
        model="deepseek-chat",
        usage=_FakeUsage(8, 4, 12),
    )
    p._sync_client_cache = _FakeSyncClient(resp)
    out = p.chat([ChatMessage(role="user", content="hi")])
    assert out.content == "hello"
    assert out.usage == {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12}
    assert out.model == "deepseek-chat"
    call = p._sync_client_cache.chat.completions.calls[0]
    assert call["model"] == "deepseek-chat"
    assert call["temperature"] == 0.7
    # 没传 max_tokens → 不应出现在 kwargs
    assert "max_tokens" not in call


def test_chat_passes_max_tokens_when_set(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    resp = _FakeChatResponse("hi")
    p._sync_client_cache = _FakeSyncClient(resp)
    p.chat([ChatMessage(role="user", content="hi")], max_tokens=256)
    call = p._sync_client_cache.chat.completions.calls[0]
    assert call["max_tokens"] == 256


def test_chat_no_usage(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    resp = _FakeChatResponse("hi", usage=None)
    p._sync_client_cache = _FakeSyncClient(resp)
    out = p.chat([ChatMessage(role="user", content="hi")])
    assert out.usage == {}


def test_chat_uses_explicit_model(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x", default_model="default-m")
    resp = _FakeChatResponse("hi", model="explicit-m")
    p._sync_client_cache = _FakeSyncClient(resp)
    p.chat([ChatMessage(role="user", content="hi")], model="explicit-m")
    call = p._sync_client_cache.chat.completions.calls[0]
    assert call["model"] == "explicit-m"


# ---------------------------------------------------------------------------
# structured()
# ---------------------------------------------------------------------------


def test_structured_unavailable_raises():
    p = OpenAICompatProvider(name="custom")
    with pytest.raises(RuntimeError, match="not configured"):
        p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})


def test_structured_injects_response_format_for_whitelisted(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    resp = _FakeChatResponse('{"answer": "ok"}', usage=None)
    p._sync_client_cache = _FakeSyncClient(resp)
    from kb_qa_agent.providers import structured as structured_mod
    monkeypatch.setattr(structured_mod, "parse_json_response", lambda text, schema: {"answer": "ok"})
    p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})
    call = p._sync_client_cache.chat.completions.calls[0]
    assert call.get("response_format") == {"type": "json_object"}


def test_structured_no_response_format_for_custom_provider(monkeypatch):
    p = OpenAICompatProvider(name="custom-vllm", api_key="k", base_url="https://x")
    resp = _FakeChatResponse('{"answer": "ok"}', usage=None)
    p._sync_client_cache = _FakeSyncClient(resp)
    from kb_qa_agent.providers import structured as structured_mod
    monkeypatch.setattr(structured_mod, "parse_json_response", lambda text, schema: {"answer": "ok"})
    p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})
    call = p._sync_client_cache.chat.completions.calls[0]
    assert "response_format" not in call


def test_structured_retry_then_succeed(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    responses = iter([
        _FakeChatResponse("not json", usage=None),
        _FakeChatResponse('{"answer": "ok"}', usage=None),
    ])
    fake_client = _FakeSyncClient(None)

    def fake_create(**kw):
        return next(responses)

    fake_client.chat.completions.create = fake_create
    p._sync_client_cache = fake_client
    from kb_qa_agent.providers import structured as structured_mod

    results = iter([ValueError("bad json"), {"answer": "ok"}])

    def fake_parse(text, schema):
        v = next(results)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(structured_mod, "parse_json_response", fake_parse)
    out = p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})
    assert out == {"answer": "ok"}


def test_structured_retry_exhausted_raises(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    p._sync_client_cache = _FakeSyncClient(_FakeChatResponse("x"))
    from kb_qa_agent.providers import structured as structured_mod

    def boom(text, schema):
        raise ValueError("always fail")

    monkeypatch.setattr(structured_mod, "parse_json_response", boom)
    with pytest.raises(ValueError, match="always fail"):
        p.structured([ChatMessage(role="user", content="x")], schema={"type": "object"})


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


class _FakeStreamChunk:
    def __init__(self, content, finish_reason=None, usage=None):
        self.choices = [type("C", (), {
            "delta": type("D", (), {"content": content})(),
            "finish_reason": finish_reason,
        })()]
        self.usage = usage


class _FakeAsyncStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for c in self._chunks:
            yield c


class _FakeAsyncCompletions:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        return _FakeAsyncStream(self._chunks)


class _FakeAsyncChatNamespace:
    def __init__(self, chunks):
        self.completions = _FakeAsyncCompletions(chunks)


class _FakeAsyncClient:
    def __init__(self, chunks):
        self.chat = _FakeAsyncChatNamespace(chunks)


@pytest.mark.asyncio
async def test_stream_unavailable_raises():
    p = OpenAICompatProvider(name="custom")
    with pytest.raises(RuntimeError, match="not configured"):
        async for _ in p.stream([ChatMessage(role="user", content="x")]):
            pass


@pytest.mark.asyncio
async def test_stream_yields_chunks_then_done():
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    usage = _FakeUsage(5, 3, 8)
    chunks = [
        _FakeStreamChunk("hi "),
        _FakeStreamChunk("world", finish_reason="stop", usage=usage),
    ]
    p._async_client_cache = _FakeAsyncClient(chunks)
    seen = []
    async for piece in p.stream([ChatMessage(role="user", content="hi")]):
        seen.append(piece)
    assert seen[0].delta == "hi "
    assert seen[0].done is False
    assert seen[1].delta == "world"
    assert seen[1].done is True
    assert seen[1].usage == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}


@pytest.mark.asyncio
async def test_stream_skips_chunks_without_choices():
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")

    class EmptyChunk:
        choices = []

    chunks = [EmptyChunk(), _FakeStreamChunk("x")]
    p._async_client_cache = _FakeAsyncClient(chunks)
    seen = []
    async for piece in p.stream([ChatMessage(role="user", content="hi")]):
        seen.append(piece)
    assert len(seen) == 1
    assert seen[0].delta == "x"


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------


def test_count_tokens_empty():
    p = OpenAICompatProvider(name="x", api_key="k", base_url="u")
    assert p.count_tokens("") == 0


def test_count_tokens_ascii():
    p = OpenAICompatProvider(name="x", api_key="k", base_url="u")
    # 12 ascii → 3 tokens
    assert p.count_tokens("hello world!") == 3


def test_count_tokens_cjk():
    p = OpenAICompatProvider(name="x", api_key="k", base_url="u")
    # 6 cjk → int(6/1.5) = 4
    assert p.count_tokens("你好世界你好") == 4


# ---------------------------------------------------------------------------
# price_per_1k
# ---------------------------------------------------------------------------


def test_price_per_1k():
    p = OpenAICompatProvider(
        name="deepseek", api_key="k", base_url="u",
        input_price_per_1k=0.14, output_price_per_1k=0.28,
    )
    assert p.price_per_1k("any", "input") == 0.14
    assert p.price_per_1k("any", "output") == 0.28


# ---------------------------------------------------------------------------
# 客户端懒加载
# ---------------------------------------------------------------------------


def test_sync_client_lazy(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    assert p._sync_client_cache is None
    c1 = p._sync_client()
    assert c1 is p._sync_client_cache
    c2 = p._sync_client()
    assert c2 is c1  # 不重复构造


def test_async_client_lazy(monkeypatch):
    p = OpenAICompatProvider(name="deepseek", api_key="k", base_url="https://x")
    assert p._async_client_cache is None
    c1 = p._async_client()
    assert c1 is p._async_client_cache
    c2 = p._async_client()
    assert c2 is c1
