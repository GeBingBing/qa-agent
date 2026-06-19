"""domains/hr/ — 人事域工具。

工具列表（注册到 GLOBAL_REGISTRY）：
  query_leave_balance(employee_id)        查询员工假期余额
  query_leave_history(employee_id)         查询员工假期申请历史
  query_attendance_policy()                 查询考勤制度要点
"""

from __future__ import annotations

from .._common import load_mock
from ...core.tool_registry import GLOBAL_REGISTRY


def query_leave_balance(employee_id: str) -> dict:
    """查询某员工的假期余额（年假 / 病假）。"""
    data = load_mock("hr")
    emp = data.get("employees", {}).get(employee_id)
    if not emp:
        return {"error": f"employee_id={employee_id!r} not found"}
    return {
        "employee_id": employee_id,
        "name": emp["name"],
        "annual_leave": {
            "quota_days": emp["annual_leave_quota_days"],
            "used_days": emp["annual_leave_used_days"],
            "remaining_days": emp["annual_leave_remaining_days"],
        },
        "sick_leave_used_days": emp["sick_leave_used_days"],
    }


def query_leave_history(employee_id: str, *, limit: int = 10) -> dict:
    """查询某员工的假期申请历史。"""
    data = load_mock("hr")
    requests = [r for r in data.get("leave_requests", []) if r["employee_id"] == employee_id]
    return {
        "employee_id": employee_id,
        "count": len(requests[:limit]),
        "requests": requests[:limit],
    }


def query_attendance_policy() -> dict:
    """返回考勤制度要点（硬编码，因为是从 HR 政策文档抽出来的）。"""
    return {
        "work_hours": "09:00 - 18:00 (弹性 ±1h)",
        "annual_leave_policy": "工作满 1 年 5 天，满 5 年 10 天，满 10 年 15 天",
        "advance_notice_days": 3,
        "approval_chain": "直属经理 → HR BP",
        "notes": "连续 3 天以上年假需提前 7 天申请；事假与病假按实际天数扣减。",
    }


# ---------- 注册到 GLOBAL_REGISTRY ----------
def register() -> None:
    GLOBAL_REGISTRY.register(
        id="query_leave_balance",
        desc="查询某员工的年假/病假余额（参数：employee_id）",
        func=query_leave_balance,
        side_effect_level="read",
        domain="hr",
        input_schema={
            "type": "object",
            "properties": {"employee_id": {"type": "string", "description": "员工 ID，如 E001"}},
            "required": ["employee_id"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="query_leave_history",
        desc="查询某员工的假期申请历史（参数：employee_id, limit?）",
        func=query_leave_history,
        side_effect_level="read",
        domain="hr",
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "limit": {"type": "integer", "description": "最多返回条数，默认 10"},
            },
            "required": ["employee_id"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="query_attendance_policy",
        desc="查询公司考勤制度要点（无参数）",
        func=query_attendance_policy,
        side_effect_level="read",
        domain="hr",
    )


__all__ = ["register", "query_leave_balance", "query_leave_history", "query_attendance_policy"]
