"""internal_mcp_client.py — 本地 mock MCP 客户端。

对应的 MCP server 在 `backend/mock_mcp_servers/internal_systems_mcp.py`
（用 FastMCP 实现），启动后监听 8765 端口，把 4 领域的工具暴露成 MCP 工具。

业务层调用本客户端 → HTTP JSON-RPC → mock MCP server → 返回数据。
"""

from __future__ import annotations

from typing import Any

import httpx

from ..providers import _get_env


class InternalMCPClient:
    """本地 mock MCP 客户端。"""

    def __init__(self, url: str | None = None, *, timeout: float = 10.0):
        self.url = url or _get_env("INTERNAL_MCP_URL", "http://localhost:8765/mcp")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.url)

    async def list_tools(self) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self.url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("result", {}).get("tools", [])
        except Exception as exc:
            return [{"error": f"internal_mcp_unreachable: {exc}"}]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """通过 JSON-RPC 调一个工具。"""
        if not self.available():
            raise RuntimeError("INTERNAL_MCP_URL not configured.")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.url,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments or {}},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {"error": "no_result"})


__all__ = ["InternalMCPClient"]
