"""domains/finance/ — 财务域工具。

工具列表：
  query_expense_policy(category)         查询某类别的报销规则
  query_department_budget(department)    查询某部门年度预算
  query_payment_status(payment_id)        查询某笔付款状态
"""

from __future__ import annotations

from .._common import load_mock
from ...core.tool_registry import GLOBAL_REGISTRY


def query_expense_policy(category: str) -> dict:
    """查询某类别（travel / meals / office_supplies）的报销规则。"""
    data = load_mock("finance")
    policy = data.get("expense_policies", {}).get(category.lower())
    if not policy:
        return {"error": f"category={category!r} not found; known: travel/meals/office_supplies"}
    return policy


def query_department_budget(department: str) -> dict:
    """查询某部门年度预算使用情况。"""
    data = load_mock("finance")
    budget = data.get("budgets", {}).get(department.lower())
    if not budget:
        return {"error": f"department={department!r} not found; known: engineering/marketing/finance"}
    return {"department": department, **budget}


def query_payment_status(payment_id: str) -> dict:
    """查询某笔付款的状态。"""
    data = load_mock("finance")
    for p in data.get("payments", []):
        if p["id"] == payment_id:
            return p
    return {"error": f"payment_id={payment_id!r} not found"}


def register() -> None:
    GLOBAL_REGISTRY.register(
        id="query_expense_policy",
        desc="查询某类别的报销规则（参数：category ∈ travel/meals/office_supplies）",
        func=query_expense_policy,
        side_effect_level="read",
        domain="finance",
        input_schema={
            "type": "object",
            "properties": {"category": {"type": "string"}},
            "required": ["category"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="query_department_budget",
        desc="查询某部门年度预算（参数：department ∈ engineering/marketing/finance）",
        func=query_department_budget,
        side_effect_level="read",
        domain="finance",
        input_schema={
            "type": "object",
            "properties": {"department": {"type": "string"}},
            "required": ["department"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="query_payment_status",
        desc="查询某笔付款状态（参数：payment_id，如 P001）",
        func=query_payment_status,
        side_effect_level="read",
        domain="finance",
        input_schema={
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": ["payment_id"],
        },
    )


__all__ = ["register", "query_expense_policy", "query_department_budget", "query_payment_status"]
