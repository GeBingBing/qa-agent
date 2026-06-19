"""OpenAI 协议兼容的 Provider 通用实现。

适用：openai / dashscope / deepseek / kimi / glm / minimax / vllm 自托管等
凡是 endpoint 长得像 /v1/chat/completions 的，都走这个类。

差异点（base_url / api_key / default_model）通过 __init__ 注入。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from openai import AsyncOpenAI, OpenAI

from .base import ChatMessage, ChatResponse, StreamChunk, _coerce_messages, _get_env
from .env_keys import api_key_env, base_url_env, default_model_env


class OpenAICompatProvider:
    """走 OpenAI 兼容协议的 Provider。"""

    def __init__(
        self,
        *,
        name: str,
        api_key: str = "",
        base_url: str = "",
        default_model: str = "",
        # 定价（USD / 1k token），可被 .env 或 SETTINGS.yaml 覆盖
        input_price_per_1k: float = 0.0,
        output_price_per_1k: float = 0.0,
    ):
        self.name = name
        self.api_key = api_key or _get_env(self._env_key_for(name))
        self.base_url = base_url or _get_env(self._env_base_for(name))
        self.default_model = default_model or _get_env(self._env_model_for(name))
        self.input_price_per_1k = input_price_per_1k
        self.output_price_per_1k = output_price_per_1k
        self._sync_client_cache: OpenAI | None = None
        self._async_client_cache: AsyncOpenAI | None = None

    # ---------------- meta ----------------

    @staticmethod
    def _env_key_for(name: str) -> str:
        return api_key_env(name)

    @staticmethod
    def _env_base_for(name: str) -> str:
        return base_url_env(name)

    @staticmethod
    def _env_model_for(name: str) -> str:
        return default_model_env(name)

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    # ---------------- clients ----------------

    def _sync_client(self) -> OpenAI:
        if self._sync_client_cache is None:
            self._sync_client_cache = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._sync_client_cache

    def _async_client(self) -> AsyncOpenAI:
        if self._async_client_cache is None:
            self._async_client_cache = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._async_client_cache

    # ---------------- public API ----------------

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
            raise RuntimeError(f"Provider {self.name!r} not configured (missing api_key/base_url).")
        client = self._sync_client()
        resp = client.chat.completions.create(
            model=model or self.default_model,
            messages=_coerce_messages(messages),  # type: ignore[arg-type]
            temperature=temperature,
            **({"max_tokens": max_tokens} if max_tokens else {}),
            **kwargs,
        )
        usage = {}
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
        return ChatResponse(
            content=(resp.choices[0].message.content or ""),
            usage=usage,
            model=getattr(resp, "model", model or self.default_model),
            raw=resp,
        )

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
        """通过 system prompt 注入 schema + 强约束 json_mode，让模型返回 JSON。

        严格的 JSON 解析 + 一次重试（重试时把错误回灌给模型）。
        """
        from .structured import build_structured_messages, parse_json_response

        if not self.available():
            raise RuntimeError(f"Provider {self.name!r} not configured.")
        merged = build_structured_messages(messages, schema)
        supports = self.supports_response_formats()
        extra: dict[str, Any] = {}
        if "json_object" in supports:
            extra["response_format"] = {"type": "json_object"}
        for attempt in range(2):
            try:
                resp = self.chat(
                    merged,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra,
                    **kwargs,
                )
                return parse_json_response(resp.content, schema)
            except Exception as exc:  # noqa: BLE001
                if attempt == 1:
                    raise
                # 把错误回灌给模型做一次自我修正
                merged.append(ChatMessage(role="user", content=f"上一轮输出未通过校验：{exc}。请重新输出 JSON。"))

        raise RuntimeError("unreachable")

    # 已知支持 OpenAI 风格 `response_format={"type": "json_object"}` 的 provider。
    # 自托管 / 未列表的 provider 默认不强制注入，避免触发 SDK 拒绝。
    _JSON_OBJECT_PROVIDERS: frozenset[str] = frozenset({
        "openai", "deepseek", "dashscope", "glm", "kimi", "minimax",
    })

    def supports_response_formats(self) -> set[str]:
        """返回该 provider 支持的 response_format 选项集合。"""
        if self.name in self._JSON_OBJECT_PROVIDERS:
            return {"json_object"}
        return set()

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
            raise RuntimeError(f"Provider {self.name!r} not configured.")
        client = self._async_client()
        stream = await client.chat.completions.create(
            model=model or self.default_model,
            messages=_coerce_messages(messages),  # type: ignore[arg-type]
            temperature=temperature,
            stream=True,
            **({"max_tokens": max_tokens} if max_tokens else {}),
            **kwargs,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            done = bool(getattr(chunk.choices[0], "finish_reason", None))
            usage = None
            if getattr(chunk, "usage", None):
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }
            yield StreamChunk(delta=delta, done=done, usage=usage, raw=chunk)

    def count_tokens(self, text: str, *, model: str | None = None) -> int:
        """粗略估算：中文 1.5 字符/token，英文 4 字符/token。

        生产可换 tiktoken，但多数 OpenAI 兼容 provider 不共享同一 tokenizer。
        """
        if not text:
            return 0
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        cjk_chars = len(text) - ascii_chars
        # ASCII: 4 chars/token; CJK: 1.5 chars/token
        return int(ascii_chars / 4 + cjk_chars / 1.5)

    def price_per_1k(self, model: str, direction: Literal["input", "output"]) -> float:
        return self.input_price_per_1k if direction == "input" else self.output_price_per_1k
