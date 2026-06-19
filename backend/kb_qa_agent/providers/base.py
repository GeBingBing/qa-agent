"""BaseProvider — 7 Provider 适配层的统一接口。

设计要点：
- 仅一个 `chat` / `structured` / `stream` 三件套，业务层不感知协议差异
- `available()` 在没有 API key 时返回 False，让上层优雅降级
- `price_per_1k()` 抽象出"成本感知"接口，配合 `observability/cost.py` 累计
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChatMessage:
    """单条对话消息。role ∈ {"system","user","assistant","tool"}"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(slots=True)
class ChatResponse:
    """非流式响应。"""

    content: str
    usage: dict[str, int] = field(default_factory=dict)  # {"prompt_tokens","completion_tokens","total_tokens"}
    model: str = ""
    raw: Any = None


@dataclass(slots=True)
class StreamChunk:
    """流式响应的单个 chunk。"""

    delta: str
    done: bool = False
    usage: dict[str, int] | None = None
    raw: Any = None


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class BaseProvider(Protocol):
    """所有 Provider 必须实现的最小接口。

    业务层只依赖这三个方法 + available() / price_per_1k()。
    """

    name: str

    def available(self) -> bool:
        """是否配置了 API key，能真正发请求。"""
        ...

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """同步单次请求。"""
        ...

    def structured(
        self,
        messages: list[ChatMessage],
        schema: dict[str, Any],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """结构化输出。Provider 应尽力遵循 schema；不保证 100% 符合。"""
        ...

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """异步流式输出。"""
        ...

    def count_tokens(self, text: str, *, model: str | None = None) -> int:
        """估算 token 数。Provider 没实现时退化为粗略字符数 / 4。"""
        ...

    def price_per_1k(self, model: str, direction: Literal["input", "output"]) -> float:
        """按 1k token 计费 (USD)。返回 0.0 = 未定价。"""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_env(name: str, default: str = "") -> str:
    """读取环境变量，trim 空白；空字符串视作未配置。"""
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else default


def _coerce_messages(messages: list[ChatMessage] | list[dict]) -> list[dict]:
    """统一把 ChatMessage 序列化为 dict，便于透传给各 Provider SDK。"""
    out = []
    for msg in messages:
        if isinstance(msg, ChatMessage):
            out.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    **({"name": msg.name} if msg.name else {}),
                    **({"tool_call_id": msg.tool_call_id} if msg.tool_call_id else {}),
                }
            )
        elif isinstance(msg, dict):
            out.append(msg)
        else:
            raise TypeError(f"Unsupported message type: {type(msg)}")
    return out
