"""registry.py — PROVIDER_REGISTRY，key=provider 名称。

业务层用 `get_provider("deepseek")` / `list_available()` 拿到实例，
不需要关心它是 OpenAI 兼容还是 Anthropic。
"""

from __future__ import annotations

import os
from typing import Any

from .base import BaseProvider, _get_env
from .claude import ClaudeProvider
from .openai_compat import OpenAICompatProvider


# ---------------------------------------------------------------------------
# 默认定价（USD / 1k tokens）
# ---------------------------------------------------------------------------
# 来源：各 Provider 官方价目。维护频率低；用户可在 .env 之外覆盖。
# 注：这些是公开参考价，会随时间变化；用作 cost 估算，不是计费凭据。
_DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "deepseek":   {"input": 0.00014, "output": 0.00028},    # deepseek-chat
    "openai":     {"input": 0.00015, "output": 0.00060},    # gpt-4o-mini
    "opus":       {"input": 0.015,   "output": 0.075},      # claude-opus-4-8
    "kimi":       {"input": 0.001,   "output": 0.002},      # moonshot-v1-128k
    "glm":        {"input": 0.0001,  "output": 0.0001},     # glm-4-flash
    "dashscope":  {"input": 0.0008,  "output": 0.002},      # qwen-plus
    "minimax":    {"input": 0.001,   "output": 0.001},      # placeholder
}


def _build_registry() -> dict[str, BaseProvider]:
    registry: dict[str, BaseProvider] = {}

    # 6 OpenAI-compatible
    for name in ("deepseek", "openai", "kimi", "glm", "dashscope", "minimax"):
        prices = _DEFAULT_PRICES.get(name, {"input": 0.0, "output": 0.0})
        registry[name] = OpenAICompatProvider(
            name=name,
            input_price_per_1k=prices["input"],
            output_price_per_1k=prices["output"],
        )

    # Claude / Opus
    opus_prices = _DEFAULT_PRICES["opus"]
    registry["opus"] = ClaudeProvider(
        input_price_per_1k=opus_prices["input"],
        output_price_per_1k=opus_prices["output"],
    )

    return registry


PROVIDER_REGISTRY: dict[str, BaseProvider] = _build_registry()


def get_provider(name: str) -> BaseProvider:
    if name not in PROVIDER_REGISTRY:
        raise KeyError(
            f"Unknown provider: {name!r}. Available: {sorted(PROVIDER_REGISTRY)}"
        )
    return PROVIDER_REGISTRY[name]


def list_available() -> list[str]:
    """返回当前有 API key 可用的 provider 列表。"""
    return [name for name, p in PROVIDER_REGISTRY.items() if p.available()]


def list_all() -> list[str]:
    return sorted(PROVIDER_REGISTRY)


def active_provider() -> tuple[str, BaseProvider]:
    """根据环境变量 KB_QA_ACTIVE_PROVIDER 返回 (name, instance)。"""
    name = os.environ.get("KB_QA_ACTIVE_PROVIDER", "deepseek").strip() or "deepseek"
    if name not in PROVIDER_REGISTRY:
        raise KeyError(f"KB_QA_ACTIVE_PROVIDER={name!r} not in registry; available: {sorted(PROVIDER_REGISTRY)}")
    return name, PROVIDER_REGISTRY[name]
