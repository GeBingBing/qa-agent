"""共享 fixture & 测试辅助。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

# 让所有测试都能 import kb_qa_agent
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Fake Provider — mock LLM 调用，不依赖网络
# ---------------------------------------------------------------------------


class FakeProvider:
    """实现 BaseProvider 协议的假 Provider，用于隔离测试 LLM 调用。"""

    name = "fake"

    def __init__(self):
        # 测试可以预设 structured 的返回值
        self.structured_response: dict[str, Any] = {"ok": True}
        self.chat_response_text: str = "(fake answer)"
        self.stream_chunks: list[str] = ["fake ", "stream"]
        self._configured: bool = True
        # 记录调用，便于断言
        self.calls: list[dict[str, Any]] = []

    def available(self) -> bool:
        return self._configured

    def chat(self, messages, *, model=None, temperature=0.7, max_tokens=None, **kw):
        from kb_qa_agent.providers.base import ChatResponse
        self.calls.append({"method": "chat", "messages": messages, "model": model})
        return ChatResponse(
            content=self.chat_response_text,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            model=model or "fake-model",
            raw=None,
        )

    def structured(self, messages, schema, *, model=None, temperature=0.3, max_tokens=None, **kw):
        self.calls.append({"method": "structured", "messages": messages, "schema": schema, "model": model})
        return self.structured_response

    async def stream(self, messages, *, model=None, temperature=0.7, max_tokens=None, **kw):
        from kb_qa_agent.providers.base import StreamChunk
        self.calls.append({"method": "stream", "messages": messages})
        for c in self.stream_chunks:
            yield StreamChunk(delta=c)
        yield StreamChunk(delta="", done=True, usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    def count_tokens(self, text, *, model=None) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    def price_per_1k(self, model, direction):
        return 0.0


@pytest.fixture
def fake_provider(monkeypatch):
    """注入 FakeProvider 到 PROVIDER_REGISTRY，让 active_provider() 返回它。"""
    from kb_qa_agent.providers import registry as registry_mod

    fake = FakeProvider()
    monkeypatch.setitem(registry_mod.PROVIDER_REGISTRY, "fake", fake)
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "fake")
    return fake


# ---------------------------------------------------------------------------
# 各种通用 fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_registry():
    """每个测试前清空 GLOBAL_REGISTRY，避免互相污染。"""
    from kb_qa_agent.core.tool_registry import GLOBAL_REGISTRY
    saved = dict(GLOBAL_REGISTRY._tools)
    GLOBAL_REGISTRY._tools.clear()
    yield GLOBAL_REGISTRY
    GLOBAL_REGISTRY._tools.clear()
    GLOBAL_REGISTRY._tools.update(saved)


@pytest.fixture
def reset_bootstrap():
    """重置 domains.bootstrap 幂等标志，让测试可重新注册。"""
    from kb_qa_agent.domains import reset_bootstrap_flag
    reset_bootstrap_flag()
    yield
    reset_bootstrap_flag()


@pytest.fixture(autouse=True)
def reset_config_cache():
    """每个测试都清 config 缓存，避免 SETTINGS.yaml 缓存影响测试。"""
    from kb_qa_agent.config import reset_config_cache
    reset_config_cache()
    yield
    reset_config_cache()
