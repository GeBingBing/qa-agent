"""测试 providers/agently_adapter.py — Agently 全局 settings 注入。

覆盖：
  - configure_agently_for_active_provider 默认 deepseek
  - env KB_QA_ACTIVE_PROVIDER 覆盖
  - KB_QA_ACTIVE_PROVIDER=opus → _configure_claude
  - 缺 api_key → 返回 configured=False + reason
  - claude 配置即缺 key 也返回 placeholder settings（不让 Agently 真调）
  - _configure_openai_compat 注入 settings 到 Agently.set_settings
"""

from __future__ import annotations

import pytest


class _FakeAgently:
    """记录 Agently.set_settings 调用。"""

    def __init__(self):
        self.calls: list[tuple[str, dict, dict]] = []

    def set_settings(self, key, settings, **kw):
        self.calls.append((key, settings, kw))
        return self


@pytest.fixture
def fake_agently(monkeypatch):
    """把 agently.Agently 替换为 fake，记录所有 set_settings 调用。"""
    from kb_qa_agent.providers import agently_adapter as mod
    fake = _FakeAgently()
    monkeypatch.setattr(mod, "Agently", fake)
    return fake


def test_configure_active_provider_default_is_deepseek(fake_agently, monkeypatch):
    monkeypatch.delenv("KB_QA_ACTIVE_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    from kb_qa_agent.providers import agently_adapter as mod
    res = mod.configure_agently_for_active_provider()
    # 缺 key → configured=False
    assert res == {"provider": "deepseek", "configured": False, "reason": "missing API key"}
    # 没有 set_settings 调用
    assert fake_agently.calls == []


def test_configure_active_provider_with_key(fake_agently, monkeypatch):
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_DEFAULT_MODEL", "deepseek-chat")

    from kb_qa_agent.providers import agently_adapter as mod
    res = mod.configure_agently_for_active_provider()
    assert res["provider"] == "deepseek"
    assert res["configured"] is True
    assert res["base_url"] == "https://api.deepseek.com"
    assert res["model"] == "deepseek-chat"
    # set_settings 被调用，auto_load_env=False
    assert len(fake_agently.calls) == 1
    key, settings, kw = fake_agently.calls[0]
    assert key == "OpenAICompatible"
    assert settings["model"] == "deepseek-chat"
    assert settings["auth"] == "sk-test"
    assert settings["base_url"] == "https://api.deepseek.com"
    assert settings["model_type"] == "chat"
    assert kw.get("auto_load_env") is False


def test_configure_active_provider_opus_no_key(fake_agently, monkeypatch):
    """opus provider 缺 ANTHROPIC_API_KEY → 配置占位 + note。"""
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "opus")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from kb_qa_agent.providers import agently_adapter as mod
    res = mod.configure_agently_for_active_provider()
    assert res["provider"] == "opus"
    assert res["configured"] is False
    assert "ANTHROPIC_API_KEY" in res["reason"]


def test_configure_active_provider_opus_with_key(fake_agently, monkeypatch):
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "opus")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setenv("ANTHROPIC_DEFAULT_MODEL", "claude-opus-4-8")

    from kb_qa_agent.providers import agently_adapter as mod
    res = mod.configure_agently_for_active_provider()
    assert res["provider"] == "opus"
    assert res["configured"] is True
    assert res["note"]
    # 即使配置成功也写一个占位 OpenAICompatible settings（Agently 内置不走真实调用）
    assert len(fake_agently.calls) == 1
    key, settings, _ = fake_agently.calls[0]
    assert key == "OpenAICompatible"
    assert settings["auth"] == ""  # 占位


def test_configure_openai_compat_missing_key(fake_agently, monkeypatch):
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "kimi")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    from kb_qa_agent.providers import agently_adapter as mod
    res = mod.configure_agently_for_active_provider()
    assert res["configured"] is False
    assert res["reason"] == "missing API key"


def test_active_provider_env_empty_string_defaults_to_deepseek(fake_agently, monkeypatch):
    """KB_QA_ACTIVE_PROVIDER='' → 走 deepseek。"""
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    from kb_qa_agent.providers import agently_adapter as mod
    res = mod.configure_agently_for_active_provider()
    assert res["provider"] == "deepseek"


def test_active_provider_env_whitespace_stripped(fake_agently, monkeypatch):
    """KB_QA_ACTIVE_PROVIDER='  kimi  ' → strip 后取 'kimi'。"""
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "  kimi  ")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    from kb_qa_agent.providers import agently_adapter as mod
    res = mod.configure_agently_for_active_provider()
    assert res["provider"] == "kimi"


def test_helper_dispatch():
    """_env_key / _env_base / _env_model 透传到 env_keys。"""
    from kb_qa_agent.providers import agently_adapter as mod
    assert mod._env_key("deepseek") == "DEEPSEEK_API_KEY"
    assert mod._env_base("dashscope") == "DASHSCOPE_BASE_URL"
    assert mod._env_model("minimax") == "MINIMAX_DEFAULT_MODEL"
