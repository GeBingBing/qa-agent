"""测试 providers.env_keys 单一来源。

P0-8：openai_compat 与 agently_adapter 不再各自维护 env-var 表，
任何新 provider 只需要在 env_keys.py 中登记。
"""

from __future__ import annotations

from kb_qa_agent.providers import env_keys
from kb_qa_agent.providers.agently_adapter import _env_base, _env_key, _env_model
from kb_qa_agent.providers.openai_compat import OpenAICompatProvider

KNOWN = ["openai", "deepseek", "kimi", "glm", "dashscope", "minimax"]


def test_env_keys_module_exposes_known_providers():
    for name in KNOWN:
        assert env_keys.api_key_env(name).endswith("_API_KEY")
        assert env_keys.base_url_env(name).endswith("_BASE_URL")
        assert env_keys.default_model_env(name).endswith("_DEFAULT_MODEL")


def test_env_keys_unknown_provider_uses_uppercase_fallback():
    assert env_keys.api_key_env("self-hosted") == "SELF-HOSTED_API_KEY"
    assert env_keys.base_url_env("self-hosted") == "SELF-HOSTED_BASE_URL"
    assert env_keys.default_model_env("self-hosted") == "SELF-HOSTED_DEFAULT_MODEL"


def test_openai_compat_uses_env_keys_module():
    """OpenAICompatProvider 内部应直接调用 env_keys，行为与模块一致。"""
    for name in KNOWN:
        assert OpenAICompatProvider._env_key_for(name) == env_keys.api_key_env(name)
        assert OpenAICompatProvider._env_base_for(name) == env_keys.base_url_env(name)
        assert OpenAICompatProvider._env_model_for(name) == env_keys.default_model_env(name)


def test_agently_adapter_uses_env_keys_module():
    for name in KNOWN:
        assert _env_key(name) == env_keys.api_key_env(name)
        assert _env_base(name) == env_keys.base_url_env(name)
        assert _env_model(name) == env_keys.default_model_env(name)
