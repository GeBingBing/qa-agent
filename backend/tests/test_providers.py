"""测试 Provider 适配层。

对应 specs/providers.spec.md。不依赖网络——通过 monkeypatch openai.OpenAI / AsyncOpenAI 完成。
"""

from __future__ import annotations

import pytest

from kb_qa_agent.providers import (
    PROVIDER_REGISTRY,
    active_provider,
    get_provider,
    list_all,
    list_available,
)
from kb_qa_agent.providers.base import ChatMessage
from kb_qa_agent.providers.openai_compat import OpenAICompatProvider
from kb_qa_agent.providers.structured import (
    build_structured_messages,
    parse_json_response,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_has_seven_providers():
    assert len(PROVIDER_REGISTRY) == 7
    assert set(list_all()) == {
        "deepseek", "openai", "opus", "kimi", "glm", "dashscope", "minimax",
    }


def test_get_unknown_provider_raises_key_error():
    with pytest.raises(KeyError, match="Unknown provider"):
        get_provider("nonexistent")


def test_active_provider_default_is_deepseek(monkeypatch):
    monkeypatch.delenv("KB_QA_ACTIVE_PROVIDER", raising=False)
    name, provider = active_provider()
    assert name == "deepseek"


def test_active_provider_respects_env(monkeypatch):
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "opus")
    name, provider = active_provider()
    assert name == "opus"


def test_active_provider_unknown_raises(monkeypatch):
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "ghost")
    with pytest.raises(KeyError):
        active_provider()


# ---------------------------------------------------------------------------
# OpenAICompatProvider
# ---------------------------------------------------------------------------


def test_provider_not_available_when_no_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    p = OpenAICompatProvider(name="deepseek")
    assert p.available() is False


def test_sync_client_is_cached(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.fake.com")
    p = OpenAICompatProvider(name="deepseek")
    a = p._sync_client()
    b = p._sync_client()
    assert a is b


def test_async_client_is_cached(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.fake.com")
    p = OpenAICompatProvider(name="deepseek")
    a = p._async_client()
    b = p._async_client()
    assert a is b


def test_provider_available_when_both_set(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.fake.com")
    p = OpenAICompatProvider(name="deepseek")
    assert p.available() is True


def test_chat_raises_when_not_configured(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    p = OpenAICompatProvider(name="deepseek")
    with pytest.raises(RuntimeError, match="not configured"):
        p.chat([ChatMessage(role="user", content="hi")])


def test_count_tokens_zero_for_empty():
    p = OpenAICompatProvider(name="fake")
    assert p.count_tokens("") == 0


def test_count_tokens_nonzero_for_text():
    p = OpenAICompatProvider(name="fake")
    assert p.count_tokens("hello world") > 0


def test_count_tokens_handles_cjk():
    p = OpenAICompatProvider(name="fake")
    n = p.count_tokens("你好世界")
    assert n > 0


def test_price_per_1k_returns_configured_rate():
    p = OpenAICompatProvider(name="fake", input_price_per_1k=0.001, output_price_per_1k=0.002)
    assert p.price_per_1k("any-model", "input") == 0.001
    assert p.price_per_1k("any-model", "output") == 0.002


# ---------------------------------------------------------------------------
# Structured 输出（schema → prompt → parse）
# ---------------------------------------------------------------------------


def test_build_structured_messages_prepends_system():
    msgs = [ChatMessage(role="user", content="hi")]
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    out = build_structured_messages(msgs, schema)
    assert len(out) == 2
    assert out[0].role == "system"
    assert "JSON Schema" in out[0].content


def test_parse_json_response_strips_code_fence():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    raw = '```json\n{"name": "Alice"}\n```'
    parsed = parse_json_response(raw, schema)
    assert parsed == {"name": "Alice"}


def test_parse_json_response_plain_json():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    parsed = parse_json_response('{"x": 42}', schema)
    assert parsed == {"x": 42}


def test_parse_json_response_missing_required_raises():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a", "b"]}
    with pytest.raises(ValueError, match="Missing required field"):
        parse_json_response('{"a": "ok"}', schema)


def test_parse_json_response_type_mismatch_raises():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    with pytest.raises(ValueError, match="expected integer"):
        parse_json_response('{"x": "not-int"}', schema)


def test_parse_json_response_strips_thinking_prefix():
    schema = {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}
    raw = '<think>先分析，但不能作为 JSON 输出。</think>\n\n{"domain": "general"}'
    parsed = parse_json_response(raw, schema)
    assert parsed == {"domain": "general"}


def test_parse_json_response_extracts_json_after_fenced_thinking():
    schema = {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}
    raw = '<think>```json\n{"domain":"bad"}\n```</think>\n\n{"domain": "general"}'
    parsed = parse_json_response(raw, schema)
    assert parsed == {"domain": "general"}


def test_parse_json_response_extracts_first_top_level_object_with_prose():
    """模型在 JSON 前后输出解释/Markdown 文本，应仍能抽出第一个顶层 {...}。"""
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    raw = (
        "好的，根据要求我输出 JSON：\n\n"
        '{"x": 42}\n\n'
        "希望对你有帮助。"
    )
    parsed = parse_json_response(raw, schema)
    assert parsed == {"x": 42}


def test_parse_json_response_handles_thinking_followed_by_prose_then_json():
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    raw = (
        "<think>分析中…</think>\n\n"
        "Sure, here is the json you asked for:\n\n"
        '{"x": 7}'
    )
    parsed = parse_json_response(raw, schema)
    assert parsed == {"x": 7}


# ---------------------------------------------------------------------------
# json_object response_format 选择（按 provider 名）
# ---------------------------------------------------------------------------


def test_supports_json_mode_only_for_known_providers(monkeypatch):
    from kb_qa_agent.providers import openai_compat as oc_mod

    p_openai = OpenAICompatProvider(name="openai")
    p_minimax = OpenAICompatProvider(name="minimax")
    p_unknown = OpenAICompatProvider(name="my-self-hosted")

    assert "json_object" in p_openai.supports_response_formats()
    assert "json_object" in p_minimax.supports_response_formats()
    # 未知 provider 默认不强制 json_object（避免下游 SDK 拒绝）
    assert "json_object" not in p_unknown.supports_response_formats()


def test_structured_omits_response_format_for_unknown_provider(monkeypatch):
    """structured() 对不支持 json_object 的 provider 不应注入 response_format。"""
    captured: dict[str, Any] = {}

    p = OpenAICompatProvider(name="my-self-hosted",
                             api_key="k", base_url="http://example")

    def fake_chat(self, messages, *, model=None, temperature=0.7, max_tokens=None, **kwargs):
        captured["kwargs"] = dict(kwargs)
        from kb_qa_agent.providers.base import ChatResponse
        return ChatResponse(content='{"x": 1}', usage={}, model=model or "x", raw=None)

    monkeypatch.setattr(OpenAICompatProvider, "chat", fake_chat, raising=True)

    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    p.structured([ChatMessage(role="user", content="hi")], schema=schema)
    assert "response_format" not in captured["kwargs"]


def test_structured_injects_response_format_for_openai_family(monkeypatch):
    captured: dict[str, Any] = {}

    p = OpenAICompatProvider(name="openai", api_key="k", base_url="http://x")

    def fake_chat(self, messages, *, model=None, temperature=0.7, max_tokens=None, **kwargs):
        captured["kwargs"] = dict(kwargs)
        from kb_qa_agent.providers.base import ChatResponse
        return ChatResponse(content='{"x": 1}', usage={}, model=model or "x", raw=None)

    monkeypatch.setattr(OpenAICompatProvider, "chat", fake_chat, raising=True)

    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    p.structured([ChatMessage(role="user", content="hi")], schema=schema)
    assert captured["kwargs"].get("response_format") == {"type": "json_object"}


def test_parse_json_response_invalid_json_raises():
    schema = {"type": "object", "properties": {}}
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_json_response("this is not json", schema)


def test_parse_json_response_top_level_array_raises():
    schema = {"type": "object", "properties": {}}
    with pytest.raises(ValueError, match="Expected dict"):
        parse_json_response("[1, 2, 3]", schema)


def test_parse_json_response_allows_bool_for_boolean_field():
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    parsed = parse_json_response('{"ok": true}', schema)
    assert parsed["ok"] is True


# ---------------------------------------------------------------------------
# list_available
# ---------------------------------------------------------------------------


def test_list_available_empty_when_no_keys(monkeypatch):
    """无 API key 时，list_available 返回空（每个 Provider 都 unavailable）。"""
    # 清掉所有可能的 key
    for prefix in ("DEEPSEEK", "OPENAI", "ANTHROPIC", "KIMI", "GLM", "DASHSCOPE", "MINIMAX"):
        monkeypatch.delenv(f"{prefix}_API_KEY", raising=False)
    # 重建 registry（因为它在 import 时就实例化了）
    from kb_qa_agent.providers.registry import _build_registry
    fresh = _build_registry()
    available_now = [n for n, p in fresh.items() if p.available()]
    assert available_now == []
