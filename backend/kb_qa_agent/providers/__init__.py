"""providers/ — 7 家 LLM Provider 适配层。

公开 API：
    from kb_qa_agent.providers import get_provider, list_available, active_provider, PROVIDER_REGISTRY
    from kb_qa_agent.providers import BaseProvider, ChatMessage, ChatResponse, StreamChunk

业务层用 `get_provider(name)` 拿到统一接口的 Provider 实例；
或用 `active_provider()` 让 .env 的 KB_QA_ACTIVE_PROVIDER 起作用。

注册顺序：deepseek / openai / opus / kimi / glm / dashscope / minimax。
详见 docs/PROVIDER_SETUP.md。
"""

from . import env_keys
from .agently_adapter import configure_agently_for_active_provider
from .base import (
    BaseProvider,
    ChatMessage,
    ChatResponse,
    StreamChunk,
)
from .claude import ClaudeProvider
from .openai_compat import OpenAICompatProvider
from .registry import (
    PROVIDER_REGISTRY,
    active_provider,
    get_provider,
    list_all,
    list_available,
)
from .structured import build_structured_messages, parse_json_response

__all__ = [
    # core types
    "BaseProvider",
    "ChatMessage",
    "ChatResponse",
    "StreamChunk",
    # concrete impls
    "OpenAICompatProvider",
    "ClaudeProvider",
    # registry
    "PROVIDER_REGISTRY",
    "get_provider",
    "list_available",
    "list_all",
    "active_provider",
    # structured helpers
    "build_structured_messages",
    "parse_json_response",
    # agently bridge
    "configure_agently_for_active_provider",
    "env_keys",
]
