"""model_request.py — 单次模型请求 + 结构化输出 + TaskExecutor。

`TaskExecutor` 把"给一坨 input → 拿回结构化 dict"封装成可复用的高层 API，
业务层不再关心 schema 提示词拼装和 JSON 解析。

走 `kb_qa_agent.providers` 适配层（统一 BaseProvider 接口），不直接调 Agently，
这样可以支持 7 家 Provider 热切换（仅改 `KB_QA_ACTIVE_PROVIDER` 环境变量）。
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from typing import Any

from ..providers import (
    PROVIDER_REGISTRY,
    BaseProvider,
    ChatMessage,
    active_provider,
    build_structured_messages,
    parse_json_response,
)
from ..providers.structured import strip_thinking_blocks

_current_override: contextvars.ContextVar[tuple[str, str | None] | None] = (
    contextvars.ContextVar("kb_qa_agent_request_provider_override", default=None)
)


@contextlib.contextmanager
def request_provider(name: str, model: str | None = None) -> Iterator[None]:
    """请求级 provider/model 覆盖。

    用法：
        with request_provider("opus", model="claude-opus-4-8"):
            classify_intent(...)            # 走 opus
            generate_plan(...)              # 走 opus
            ...

    退出 context 后恢复为原 active_provider。
    """
    if name not in PROVIDER_REGISTRY:
        raise KeyError(f"Unknown provider: {name!r}; available: {sorted(PROVIDER_REGISTRY)}")
    token = _current_override.set((name, model))
    try:
        yield
    finally:
        _current_override.reset(token)


def _resolve_active() -> tuple[str, BaseProvider, str | None]:
    override = _current_override.get()
    if override is not None:
        name, model = override
        return name, PROVIDER_REGISTRY[name], model
    name, provider = active_provider()
    return name, provider, None


class TaskExecutor:
    """统一的"单次模型请求 → 文本 / 结构化"封装。

    用法：
        executor = TaskExecutor()                         # 默认 active provider；
                                                          # 处于 request_provider context 时优先用 context
        text = executor.run_text([...])                   # 纯文本
        data = executor.run_structured([...], schema=...) # JSON
    """

    def __init__(self, provider: BaseProvider | None = None, model: str | None = None):
        if provider is not None:
            self._provider_name = provider.name
            self._provider = provider
            self._model = model
        else:
            name, prov, ctx_model = _resolve_active()
            self._provider_name = name
            self._provider = prov
            self._model = model if model is not None else ctx_model

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str | None:
        return self._model

    def run_text(
        self,
        messages: list[ChatMessage] | list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        normalized = self._coerce(messages)
        resp = self._provider.chat(
            normalized,
            model=self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return strip_thinking_blocks(resp.content)

    def run_structured(
        self,
        messages: list[ChatMessage] | list[dict],
        *,
        schema: dict[str, Any],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        normalized = self._coerce(messages)
        return self._provider.structured(
            normalized,
            schema=schema,
            model=self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def astream_text(
        self,
        messages: list[ChatMessage] | list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ):
        normalized = self._coerce(messages)
        async for chunk in self._provider.stream(
            normalized,
            model=self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk
    @staticmethod
    def _coerce(messages: list[ChatMessage] | list[dict]) -> list[ChatMessage]:
        out: list[ChatMessage] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                out.append(m)
            else:
                out.append(
                    ChatMessage(
                        role=m.get("role", "user"),
                        content=m.get("content", ""),
                        name=m.get("name"),
                        tool_call_id=m.get("tool_call_id"),
                    )
                )
        return out


# ---- convenience helpers --------------------------------------------------

def quick_text(prompt: str, *, system: str = "", **kwargs: Any) -> str:
    """最轻量的"一进一出"调用。"""
    msgs = []
    if system:
        msgs.append(ChatMessage(role="system", content=system))
    msgs.append(ChatMessage(role="user", content=prompt))
    return TaskExecutor().run_text(msgs, **kwargs)


def quick_structured(prompt: str, *, schema: dict[str, Any], system: str = "", **kwargs: Any) -> dict[str, Any]:
    msgs = []
    if system:
        msgs.append(ChatMessage(role="system", content=system))
    msgs.append(ChatMessage(role="user", content=prompt))
    return TaskExecutor().run_structured(msgs, schema=schema, **kwargs)


__all__ = [
    "TaskExecutor",
    "quick_text",
    "quick_structured",
    "ChatMessage",
    "build_structured_messages",
    "parse_json_response",
    "request_provider",
]
