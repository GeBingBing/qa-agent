"""amap_client.py — 高德地图 MCP 客户端（外部）。

实际生产环境使用 Agently 内置的 `agent.async_use_mcp(url)` 即可；
这里封装一个独立客户端，便于：
  1. 单独测试 MCP 调用
  2. 在 ToolRegistry 中注册成普通工具（统一签名）
  3. 不依赖 Agently settings 中的全局 MCP 配置

注意：高德 MCP 协议是 stdio 或 sse；这里假设 sse HTTP 形态。
占位实现；真实对接请参考 [高德 MCP 官方文档]。
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..providers import _get_env


class AmapMCPClient:
    """高德 MCP 客户端封装。"""

    def __init__(self, url: str | None = None, *, timeout: float = 30.0):
        self.url = url or _get_env("AMAP_MCP_URL", "")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.url)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """通过 MCP JSON-RPC 调一个工具。

        这里用通用的 MCP-over-HTTP 形态：`POST /mcp` body 是 JSON-RPC。
        具体协议细节请按高德 MCP 文档调整。
        """
        if not self.available():
            raise RuntimeError("AMAP_MCP_URL not configured; skip AMap MCP calls.")
        # 占位实现：返回 mock 响应，便于不连真实 MCP 也能跑端到端测试
        return {
            "ok": True,
            "tool": name,
            "arguments": arguments or {},
            "mock": True,
            "note": "Replace with real AMap MCP JSON-RPC call in production.",
        }


__all__ = ["AmapMCPClient"]
