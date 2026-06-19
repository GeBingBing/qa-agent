"""测试 4 域工具注册 + 调用。

不调 LLM；测试 domains.bootstrap 幂等性、各 domain 工具能拿到正确数据。
"""

from __future__ import annotations

import asyncio


def test_bootstrap_registers_twelve_tools(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    assert len(reset_registry.list()) == 12


def test_bootstrap_is_idempotent(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    count_after_first = len(reset_registry.list())
    bootstrap()  # 二次调用应当不再注册
    bootstrap()  # 三次也一样
    assert len(reset_registry.list()) == count_after_first


def test_bootstrap_partitions_by_domain(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    assert len(reset_registry.filter(domain="hr")) == 3
    assert len(reset_registry.filter(domain="finance")) == 3
    assert len(reset_registry.filter(domain="it")) == 3
    assert len(reset_registry.filter(domain="legal")) == 3


def test_hr_query_leave_balance_known_employee(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("query_leave_balance", employee_id="E001"))
    assert result["employee_id"] == "E001"
    assert result["name"] == "张三"
    assert result["annual_leave"]["remaining_days"] == 11


def test_hr_query_leave_balance_unknown_employee(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("query_leave_balance", employee_id="GHOST"))
    assert "error" in result


def test_finance_query_expense_policy_travel(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("query_expense_policy", category="travel"))
    assert result["per_diem_cny"] == 400
    assert result["hotel_cap_cny"] == 600


def test_finance_query_expense_policy_unknown(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("query_expense_policy", category="ghost"))
    assert "error" in result


def test_it_query_account_access(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("query_account_access", employee_id="E003"))
    assert result["aws_console_access"] == "admin"
    assert result["github_role"] == "maintainer"


def test_it_query_system_status_no_args(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("query_system_status"))
    assert "vpn_gateway" in result
    assert result["internal_wiki"]["status"] == "degraded"


def test_legal_query_contract(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("query_contract", contract_id="C001"))
    assert result["title"] == "AWS 中国服务主协议"
    assert "data_residency" in result["key_clauses"]


def test_legal_check_compliance_low_risk(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    # DPA 模板 (C003) vs GDPR (R002) → low risk
    result = asyncio.run(
        reset_registry.execute("check_compliance", contract_id="C003", regulation_id="R002")
    )
    assert result["risk"] == "low"
    assert result["issues"] == []


def test_legal_check_compliance_medium_risk(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    # AWS 主协议 (C001) vs GDPR (R002) → medium risk（无 DPA 条款）
    result = asyncio.run(
        reset_registry.execute("check_compliance", contract_id="C001", regulation_id="R002")
    )
    assert result["risk"] == "medium"
    assert len(result["issues"]) > 0


def test_legal_search_contracts_by_keyword(reset_registry, reset_bootstrap):
    from kb_qa_agent.domains import bootstrap
    bootstrap()
    result = asyncio.run(reset_registry.execute("search_contracts", keyword="DPA"))
    assert result["count"] >= 1
    titles = [c["title"] for c in result["contracts"]]
    assert any("DPA" in t for t in titles)
