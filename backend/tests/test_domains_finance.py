"""测试 domains/finance/__init__.py — 财务域三个工具。

覆盖：
  - query_expense_policy 命中 / 未命中
  - query_department_budget 命中 / 未命中
  - query_payment_status 命中 / 未命中
  - register 把三个工具注册到 GLOBAL_REGISTRY
"""

from __future__ import annotations

import pytest


@pytest.fixture
def saved_registry():
    from kb_qa_agent.core.tool_registry import GLOBAL_REGISTRY
    saved = dict(GLOBAL_REGISTRY._tools)
    yield GLOBAL_REGISTRY
    GLOBAL_REGISTRY._tools.clear()
    GLOBAL_REGISTRY._tools.update(saved)


def test_query_expense_policy_known_category(monkeypatch):
    from kb_qa_agent.domains.finance import query_expense_policy

    monkeypatch.setattr(
        "kb_qa_agent.domains.finance.load_mock",
        lambda domain: {
            "expense_policies": {
                "travel": {"max_per_day": 800, "needs_receipt": True},
                "meals": {"max_per_day": 200},
            }
        },
    )
    out = query_expense_policy("travel")
    assert out == {"max_per_day": 800, "needs_receipt": True}
    # 大小写不敏感
    assert query_expense_policy("TRAVEL") == out


def test_query_expense_policy_unknown_category(monkeypatch):
    from kb_qa_agent.domains.finance import query_expense_policy

    monkeypatch.setattr(
        "kb_qa_agent.domains.finance.load_mock",
        lambda domain: {"expense_policies": {"travel": {}}},
    )
    out = query_expense_policy("crypto")
    assert "error" in out
    assert "travel/meals/office_supplies" in out["error"]


def test_query_department_budget_known(monkeypatch):
    from kb_qa_agent.domains.finance import query_department_budget

    monkeypatch.setattr(
        "kb_qa_agent.domains.finance.load_mock",
        lambda domain: {
            "budgets": {
                "engineering": {"used": 120000, "total": 500000},
            }
        },
    )
    out = query_department_budget("Engineering")
    assert out["department"] == "Engineering"
    assert out["used"] == 120000
    assert out["total"] == 500000


def test_query_department_budget_unknown(monkeypatch):
    from kb_qa_agent.domains.finance import query_department_budget

    monkeypatch.setattr(
        "kb_qa_agent.domains.finance.load_mock",
        lambda domain: {"budgets": {"engineering": {}}},
    )
    out = query_department_budget("ghost")
    assert "error" in out


def test_query_payment_status_found(monkeypatch):
    from kb_qa_agent.domains.finance import query_payment_status

    monkeypatch.setattr(
        "kb_qa_agent.domains.finance.load_mock",
        lambda domain: {
            "payments": [
                {"id": "P001", "amount": 5000, "status": "pending"},
                {"id": "P002", "amount": 1200, "status": "paid"},
            ]
        },
    )
    assert query_payment_status("P002") == {"id": "P002", "amount": 1200, "status": "paid"}


def test_query_payment_status_not_found(monkeypatch):
    from kb_qa_agent.domains.finance import query_payment_status

    monkeypatch.setattr(
        "kb_qa_agent.domains.finance.load_mock",
        lambda domain: {"payments": [{"id": "P001"}]},
    )
    out = query_payment_status("P999")
    assert "error" in out
    assert "P999" in out["error"]


def test_register_adds_three_tools(saved_registry):
    from kb_qa_agent.domains.finance import register

    saved_registry._tools.clear()
    register()
    ids = set(saved_registry._tools.keys())
    assert ids == {"query_expense_policy", "query_department_budget", "query_payment_status"}
    for tool_id in ids:
        spec = saved_registry._tools[tool_id]
        assert spec.domain == "finance"
        assert spec.side_effect_level == "read"
        assert spec.input_schema.get("type") == "object"
