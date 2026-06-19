"""domains/it/ — IT 域工具。

工具列表：
  query_account_access(employee_id)      查询某员工的系统访问权限
  query_ticket_status(ticket_id)         查询工单状态
  query_system_status()                  查询当前 IT 系统运行状态
"""

from __future__ import annotations

from .._common import load_mock
from ...core.tool_registry import GLOBAL_REGISTRY


def query_account_access(employee_id: str) -> dict:
    """查询某员工的账号权限（VPN / AWS / GitHub 等）。"""
    data = load_mock("it")
    acc = data.get("accounts", {}).get(employee_id)
    if not acc:
        return {"error": f"employee_id={employee_id!r} not found"}
    return {"employee_id": employee_id, **acc}


def query_ticket_status(ticket_id: str) -> dict:
    """查询工单状态。"""
    data = load_mock("it")
    for t in data.get("tickets", []):
        if t["id"] == ticket_id:
            return t
    return {"error": f"ticket_id={ticket_id!r} not found"}


def query_system_status() -> dict:
    """查询当前 IT 系统运行状态。"""
    return load_mock("it").get("system_status", {})


def register() -> None:
    GLOBAL_REGISTRY.register(
        id="query_account_access",
        desc="查询某员工的系统访问权限（参数：employee_id）",
        func=query_account_access,
        side_effect_level="read",
        domain="it",
        input_schema={
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="query_ticket_status",
        desc="查询工单状态（参数：ticket_id，如 T001）",
        func=query_ticket_status,
        side_effect_level="read",
        domain="it",
        input_schema={
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="query_system_status",
        desc="查询当前 IT 系统运行状态（无参数）",
        func=query_system_status,
        side_effect_level="read",
        domain="it",
    )


__all__ = ["register", "query_account_access", "query_ticket_status", "query_system_status"]
