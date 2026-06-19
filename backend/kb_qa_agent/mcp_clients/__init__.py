"""mcp_clients/ — MCP 客户端封装。

两个 MCP：
  amap_client.py        高德地图 MCP（外部）
  internal_mcp_client.py  本地 mock MCP（自建，覆盖 4 领域工具）

业务层通过 `MCPClient.call_tool(name, **kwargs)` 调用，不感知协议。
"""

from .amap_client import AmapMCPClient
from .internal_mcp_client import InternalMCPClient

__all__ = ["AmapMCPClient", "InternalMCPClient"]
