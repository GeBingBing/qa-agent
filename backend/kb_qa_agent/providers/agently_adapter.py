"""agently_adapter.py — 把当前 Provider 注入 Agently 全局 settings。

Agently 4.x 主框架仍在内部用 `Agently.set_settings(key, value)`。
我们让当前选中的 Provider 对 Agently 表现为一个"OpenAI 兼容"后端
（Claude 单独走 Anthropic；其余 6 家全部走 OpenAI 协议）。

业务层 Agently.create_agent() 拿到的就是 Agently 内置的 chat 模型，
由本模块根据 .env 在启动时一次性注入。

注意：本项目核心模型调用走 providers/ 适配层（统一 BaseProvider 接口），
只在"Agently 原生工具调用 / Skills / MCP" 这条路径上用 Agently 内置模型。
"""

from __future__ import annotations

import os
from typing import Any

from agently import Agently

from .base import _get_env
from .claude import ClaudeProvider
from .env_keys import api_key_env, base_url_env, default_model_env
from .openai_compat import OpenAICompatProvider


def configure_agently_for_active_provider() -> dict[str, Any]:
    """根据 KB_QA_ACTIVE_PROVIDER 配置 Agently 全局 settings。

    Returns: 已写入的 settings 摘要，便于日志/调试。
    """
    provider_name = os.environ.get("KB_QA_ACTIVE_PROVIDER", "deepseek").strip() or "deepseek"

    if provider_name == "opus":
        return _configure_claude()
    return _configure_openai_compat(provider_name)


def _configure_openai_compat(provider_name: str) -> dict[str, Any]:
    api_key = _get_env(_env_key(provider_name))
    base_url = _get_env(_env_base(provider_name), "https://api.openai.com/v1")
    default_model = _get_env(_env_model(provider_name), "gpt-4o-mini")

    if not api_key:
        # 即便 Agently 跑不起来也不阻塞整个应用启动
        return {"provider": provider_name, "configured": False, "reason": "missing API key"}

    settings: dict[str, Any] = {
        "base_url": base_url,
        "model": default_model,
        "model_type": "chat",
        "auth": api_key,
    }
    Agently.set_settings("OpenAICompatible", settings, auto_load_env=False)
    return {
        "provider": provider_name,
        "configured": True,
        "base_url": base_url,
        "model": default_model,
    }


def _configure_claude() -> dict[str, Any]:
    api_key = _get_env("ANTHROPIC_API_KEY")
    base_url = _get_env("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    default_model = _get_env("ANTHROPIC_DEFAULT_MODEL", "claude-opus-4-8")
    if not api_key:
        return {"provider": "opus", "configured": False, "reason": "missing ANTHROPIC_API_KEY"}
    # Agently 4.x 是否原生支持 Anthropic 视版本而定。
    # 这里同时写一个 OpenAI 兼容占位 + 标记，让上层走 Anthropic SDK 而不是 Agently 内置。
    Agently.set_settings("OpenAICompatible", {
        "base_url": base_url,  # 占位，Agently 内置不会真正调用
        "model": default_model,
        "model_type": "chat",
        "auth": "",
    }, auto_load_env=False)
    return {
        "provider": "opus",
        "configured": True,
        "base_url": base_url,
        "model": default_model,
        "note": "Anthropic SDK calls go through providers/claude.py; Agently built-in chat is a stub for this provider.",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_key(name: str) -> str:
    return api_key_env(name)


def _env_base(name: str) -> str:
    return base_url_env(name)


def _env_model(name: str) -> str:
    return default_model_env(name)
