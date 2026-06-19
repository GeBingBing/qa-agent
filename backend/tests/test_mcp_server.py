"""测试 mock MCP server 的 JSON-RPC 处理逻辑。

不启 HTTP server；只测 handle_request 函数的正确性。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把 backend/ 加进 path 以便 import mock_mcp_servers
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def test_tools_list_returns_twelve_tools():
    from mock_mcp_servers.internal_systems_mcp import handle_request
    resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert "result" in resp
    assert len(resp["result"]["tools"]) == 12


def test_tools_list_each_has_required_fields():
    from mock_mcp_servers.internal_systems_mcp import handle_request
    resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    for tool in resp["result"]["tools"]:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


def test_tools_call_returns_tool_result():
    from mock_mcp_servers.internal_systems_mcp import handle_request
    resp = handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "query_leave_balance", "arguments": {"employee_id": "E001"}},
    })
    assert "result" in resp
    data = resp["result"]["content"][0]["data"]
    assert data["employee_id"] == "E001"
    assert data["annual_leave"]["remaining_days"] == 11


def test_tools_call_unknown_tool_returns_error():
    from mock_mcp_servers.internal_systems_mcp import handle_request
    resp = handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "ghost_tool", "arguments": {}},
    })
    assert "error" in resp
    assert "unknown tool" in resp["error"]["message"]


def test_tools_call_with_bad_arguments_returns_error():
    from mock_mcp_servers.internal_systems_mcp import handle_request
    resp = handle_request({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "query_leave_balance", "arguments": {}},  # 缺 employee_id
    })
    # 工具函数会抛 TypeError，被包装成 RPC error
    assert "error" in resp


def test_unknown_method_returns_error():
    from mock_mcp_servers.internal_systems_mcp import handle_request
    resp = handle_request({"jsonrpc": "2.0", "id": 5, "method": "unknown/foo", "params": {}})
    assert "error" in resp
    assert "unknown method" in resp["error"]["message"]


def test_jsonrpc_id_preserved():
    from mock_mcp_servers.internal_systems_mcp import handle_request
    for rpc_id in [42, "abc", None]:
        resp = handle_request({
            "jsonrpc": "2.0", "id": rpc_id, "method": "tools/list", "params": {},
        })
        assert resp["id"] == rpc_id
