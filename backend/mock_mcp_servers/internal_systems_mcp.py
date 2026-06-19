"""mock_mcp_servers/internal_systems_mcp.py — 本地 mock MCP server。

把 4 领域的工具暴露成 MCP 工具。启动：
  docker compose up mock-internal-mcp
或本地：
  python -m mock_mcp_servers.internal_systems_mcp

监听 8765 端口，提供 JSON-RPC over HTTP 形态的 MCP 接口。
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# 把 backend/ 加进 path，方便直接 python -m 调用
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from kb_qa_agent.domains import hr, finance, it, legal  # noqa: E402

PORT = 8765


# ---------------------------------------------------------------------------
# 工具目录（与 kb_qa_agent.domains/* 同步）
# ---------------------------------------------------------------------------


TOOL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "query_leave_balance",
        "description": "查询某员工的年假/病假余额（HR 域）",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "query_leave_history",
        "description": "查询某员工的假期申请历史（HR 域）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["employee_id"],
        },
    },
    {
        "name": "query_attendance_policy",
        "description": "查询公司考勤制度要点（HR 域）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "query_expense_policy",
        "description": "查询某类别的报销规则（财务域）",
        "inputSchema": {
            "type": "object",
            "properties": {"category": {"type": "string"}},
            "required": ["category"],
        },
    },
    {
        "name": "query_department_budget",
        "description": "查询某部门年度预算（财务域）",
        "inputSchema": {
            "type": "object",
            "properties": {"department": {"type": "string"}},
            "required": ["department"],
        },
    },
    {
        "name": "query_payment_status",
        "description": "查询某笔付款状态（财务域）",
        "inputSchema": {
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": ["payment_id"],
        },
    },
    {
        "name": "query_account_access",
        "description": "查询某员工的系统访问权限（IT 域）",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "query_ticket_status",
        "description": "查询工单状态（IT 域）",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "query_system_status",
        "description": "查询当前 IT 系统运行状态（IT 域）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "query_contract",
        "description": "查询某合同详情（法务域）",
        "inputSchema": {
            "type": "object",
            "properties": {"contract_id": {"type": "string"}},
            "required": ["contract_id"],
        },
    },
    {
        "name": "search_contracts",
        "description": "按关键词搜索合同（法务域）",
        "inputSchema": {
            "type": "object",
            "properties": {"keyword": {"type": "string"}},
            "required": ["keyword"],
        },
    },
    {
        "name": "check_compliance",
        "description": "对 (contract, regulation) 做合规检查（法务域）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contract_id": {"type": "string"},
                "regulation_id": {"type": "string"},
            },
            "required": ["contract_id", "regulation_id"],
        },
    },
]


# 工具名 → 函数映射（与 kb_qa_agent.domains/* 共享实现）
_TOOL_DISPATCH: dict[str, Any] = {
    "query_leave_balance":       hr.query_leave_balance,
    "query_leave_history":       hr.query_leave_history,
    "query_attendance_policy":   hr.query_attendance_policy,
    "query_expense_policy":      finance.query_expense_policy,
    "query_department_budget":   finance.query_department_budget,
    "query_payment_status":      finance.query_payment_status,
    "query_account_access":      it.query_account_access,
    "query_ticket_status":       it.query_ticket_status,
    "query_system_status":       it.query_system_status,
    "query_contract":            legal.query_contract,
    "search_contracts":          legal.search_contracts,
    "check_compliance":          legal.check_compliance,
}


# ---------------------------------------------------------------------------
# JSON-RPC 处理器
# ---------------------------------------------------------------------------


def _rpc_ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(body: dict[str, Any]) -> dict[str, Any]:
    req_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {}) or {}

    if method == "tools/list":
        return _rpc_ok(req_id, {"tools": TOOL_CATALOG})
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}
        func = _TOOL_DISPATCH.get(name)
        if not func:
            return _rpc_err(req_id, -32601, f"unknown tool: {name!r}")
        try:
            result = func(**arguments)
            return _rpc_ok(req_id, {"content": [{"type": "json", "data": result}]})
        except Exception as exc:  # noqa: BLE001
            return _rpc_err(req_id, -32000, f"tool execution failed: {exc}")

    return _rpc_err(req_id, -32601, f"unknown method: {method!r}")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            self._send(400, _rpc_err(None, -32700, f"parse error: {exc}"))
            return
        try:
            result = handle_request(body)
        except Exception as exc:  # noqa: BLE001
            result = _rpc_err(body.get("id"), -32603, f"internal error: {exc}")
        self._send(200, result)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send(200, {"status": "ok", "tools": len(TOOL_CATALOG)})
        else:
            self._send(404, {"error": "not found"})

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # noqa: A003
        # 静默默认 access log；调试时打开
        pass


def main() -> None:
    # 启动时把 4 域工具注册到 GLOBAL_REGISTRY（业务侧）
    hr.register()
    finance.register()
    it.register()
    legal.register()
    print(f"[internal_systems_mcp] listening on :{PORT}, tools={len(TOOL_CATALOG)}")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
