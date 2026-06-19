"""domains/legal/ — 法务域工具。

工具列表：
  query_contract(contract_id)            查询某合同详情
  search_contracts(keyword)               按关键词搜索合同
  check_compliance(contract_id, regulation_id) 检查合同对某法规的合规性
"""

from __future__ import annotations

from .._common import load_mock
from ...core.tool_registry import GLOBAL_REGISTRY


def query_contract(contract_id: str) -> dict:
    """查询合同详情。"""
    data = load_mock("legal")
    for c in data.get("contracts", []):
        if c["id"] == contract_id:
            return c
    return {"error": f"contract_id={contract_id!r} not found"}


def search_contracts(keyword: str) -> dict:
    """按关键词搜索合同（标题 / 对方 / 标签命中）。"""
    data = load_mock("legal")
    k = keyword.lower()
    hits = []
    for c in data.get("contracts", []):
        if (
            k in c["title"].lower()
            or k in c.get("counterparty", "").lower()
            or any(k in t.lower() for t in c.get("tags", []))
        ):
            hits.append(c)
    return {"keyword": keyword, "count": len(hits), "contracts": hits}


def check_compliance(contract_id: str, regulation_id: str) -> dict:
    """对 (contract, regulation) 做粗粒度合规检查。Mock 实现，仅基于关键词匹配。"""
    data = load_mock("legal")
    contract = next((c for c in data.get("contracts", []) if c["id"] == contract_id), None)
    regulation = next((r for r in data.get("regulations", []) if r["id"] == regulation_id), None)
    if not contract:
        return {"error": f"contract_id={contract_id!r} not found"}
    if not regulation:
        return {"error": f"regulation_id={regulation_id!r} not found"}

    # 简单规则：含 GDPR/PIPL/数据处理 DPA 关键词的合同视为合规
    has_dpa = "DPA" in contract.get("key_clauses", {}).get("data_processing_agreement", "") \
              or "DPA" in contract["title"] \
              or "GDPR" in contract.get("title", "") \
              or "个保" in contract.get("title", "")
    risk = "low" if has_dpa else "medium"
    issues = []
    if not has_dpa:
        issues.append(f"合同 {contract['title']} 未明确包含 DPA 条款，与 {regulation['name']} 要求存在差距")

    return {
        "contract_id": contract_id,
        "regulation_id": regulation_id,
        "regulation_name": regulation["name"],
        "risk": risk,
        "issues": issues,
        "recommendation": "建议补充 DPA 附录并由法务复核" if risk != "low" else "当前条款覆盖充分",
    }


def register() -> None:
    GLOBAL_REGISTRY.register(
        id="query_contract",
        desc="查询某合同详情（参数：contract_id，如 C001）",
        func=query_contract,
        side_effect_level="read",
        domain="legal",
        input_schema={
            "type": "object",
            "properties": {"contract_id": {"type": "string"}},
            "required": ["contract_id"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="search_contracts",
        desc="按关键词搜索合同（参数：keyword）",
        func=search_contracts,
        side_effect_level="read",
        domain="legal",
        input_schema={
            "type": "object",
            "properties": {"keyword": {"type": "string"}},
            "required": ["keyword"],
        },
    )
    GLOBAL_REGISTRY.register(
        id="check_compliance",
        desc="对 (contract, regulation) 做合规检查（参数：contract_id, regulation_id）",
        func=check_compliance,
        side_effect_level="read",
        domain="legal",
        input_schema={
            "type": "object",
            "properties": {
                "contract_id": {"type": "string"},
                "regulation_id": {"type": "string"},
            },
            "required": ["contract_id", "regulation_id"],
        },
    )


__all__ = ["register", "query_contract", "search_contracts", "check_compliance"]
