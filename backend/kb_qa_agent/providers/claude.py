"""Claude / Opus 适配层（Anthropic 协议）。

唯一不走 OpenAI 兼容协议的 Provider，需要单独的 SDK 调用路径。
其余 6 家都基于 OpenAI 协议。
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Literal

from .base import BaseProvider, ChatMessage, ChatResponse, StreamChunk, _coerce_messages, _get_env


class ClaudeProvider:
    """Anthropic Claude / Opus 适配。"""

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "https://api.anthropic.com",
        default_model: str = "claude-opus-4-8",
        input_price_per_1k: float = 15.0,   # Opus 4.8 input
        output_price_per_1k: float = 75.0,  # Opus 4.8 output
    ):
        self.name = "opus"
        self.api_key = api_key or _get_env("ANTHROPIC_API_KEY")
        self.base_url = base_url or _get_env("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self.default_model = default_model or _get_env("ANTHROPIC_DEFAULT_MODEL", "claude-opus-4-8")
        self.input_price_per_1k = input_price_per_1k
        self.output_price_per_1k = output_price_per_1k
        self._client = None
        self._async_client = None

    def available(self) -> bool:
        return bool(self.api_key)

    def _ensure_sync(self):
        if self._client is None:
            from anthropic import Anthropic  # type: ignore
            self._client = Anthropic(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def _ensure_async(self):
        if self._async_client is None:
            from anthropic import AsyncAnthropic  # type: ignore
            self._async_client = AsyncAnthropic(api_key=self.api_key, base_url=self.base_url)
        return self._async_client

    @staticmethod
    def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
        system_parts: list[str] = []
        rest: list[dict] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg["content"])
            else:
                rest.append(msg)
        return "\n\n".join(system_parts), rest

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        if not self.available():
            raise RuntimeError("Provider 'opus' not configured (missing ANTHROPIC_API_KEY).")
        client = self._ensure_sync()
        system, rest = self._split_system(_coerce_messages(messages))
        resp = client.messages.create(
            model=model or self.default_model,
            system=system,
            messages=rest,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )
        # resp.content is a list of ContentBlock; concat text blocks
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        usage = {}
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
                "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
            }
        return ChatResponse(content=text, usage=usage, model=resp.model, raw=resp)

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
        """Claude 提供 tool_use 做结构化输出。这里走"通用 JSON 兜底"路径以保持一致。"""
        from .structured import build_structured_messages, parse_json_response

        if not self.available():
            raise RuntimeError("Provider 'opus' not configured.")
        merged = build_structured_messages(messages, schema)
        for attempt in range(2):
            try:
                resp = self.chat(merged, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)
                return parse_json_response(resp.content, schema)
            except Exception as exc:  # noqa: BLE001
                if attempt == 1:
                    raise
                merged.append(ChatMessage(role="user", content=f"上一轮输出未通过校验：{exc}。请重新输出 JSON。"))
        raise RuntimeError("unreachable")

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        if not self.available():
            raise RuntimeError("Provider 'opus' not configured.")
        client = self._ensure_async()
        system, rest = self._split_system(_coerce_messages(messages))
        async with client.messages.stream(
            model=model or self.default_model,
            system=system,
            messages=rest,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(delta=text)
            # 流结束拿 usage
            final = await stream.get_final_message()
            usage = {}
            if getattr(final, "usage", None):
                usage = {
                    "prompt_tokens": final.usage.input_tokens,
                    "completion_tokens": final.usage.output_tokens,
                    "total_tokens": final.usage.input_tokens + final.usage.output_tokens,
                }
            yield StreamChunk(delta="", done=True, usage=usage)

    def count_tokens(self, text: str, *, model: str | None = None) -> int:
        if not text:
            return 0
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        cjk_chars = len(text) - ascii_chars
        return int(ascii_chars / 4 + cjk_chars / 1.5)

    def price_per_1k(self, model: str, direction: Literal["input", "output"]) -> float:
        return self.input_price_per_1k if direction == "input" else self.output_price_per_1k
