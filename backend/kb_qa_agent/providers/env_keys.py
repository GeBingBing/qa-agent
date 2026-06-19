"""providers/env_keys.py — Provider 环境变量名单一来源。

OpenAI 兼容族 6 家 + Anthropic 各自的 `<NAME>_API_KEY` / `<NAME>_BASE_URL` /
`<NAME>_DEFAULT_MODEL` 都集中在这里登记，避免散落多个映射表导致漂移。
"""

from __future__ import annotations


_KEY_OVERRIDES: dict[str, str] = {
    "opus": "ANTHROPIC_API_KEY",
}

_BASE_OVERRIDES: dict[str, str] = {
    "opus": "ANTHROPIC_BASE_URL",
}

_MODEL_OVERRIDES: dict[str, str] = {
    "opus": "ANTHROPIC_DEFAULT_MODEL",
}


def api_key_env(provider: str) -> str:
    if provider in _KEY_OVERRIDES:
        return _KEY_OVERRIDES[provider]
    return f"{provider.upper()}_API_KEY"


def base_url_env(provider: str) -> str:
    if provider in _BASE_OVERRIDES:
        return _BASE_OVERRIDES[provider]
    return f"{provider.upper()}_BASE_URL"


def default_model_env(provider: str) -> str:
    if provider in _MODEL_OVERRIDES:
        return _MODEL_OVERRIDES[provider]
    return f"{provider.upper()}_DEFAULT_MODEL"


__all__ = ["api_key_env", "base_url_env", "default_model_env"]
