---
name: legal-compliance-scan
description: 当用户询问合同条款 / 合规 / 法规 (PIPL/GDPR/网络安全法/数据安全法) 时调用。组合 query_contract / search_contracts / check_compliance 三个内部工具。
metadata:
  version: 1.0
  domain: legal
  install_source: builtin
  trust_level: trusted
  keywords:
    - 合同
    - 合规
    - GDPR
    - 个保法
    - 数据安全法
    - 网络安全法
    - 法规
    - contract
    - compliance
    - PIPL
allowed-tools:
  - svc:query_contract
  - svc:search_contracts
  - svc:check_compliance
---

# Legal Compliance Scan Skill

回答法务域问题。流程：

1. 识别是"查询合同"还是"合规审查"还是"法规咨询"
2. 合同详情：调用 `query_contract(contract_id)`
3. 关键词搜索：调用 `search_contracts(keyword)`
4. 合规审查：调用 `check_compliance(contract_id, regulation_id)`，覆盖：
   - PIPL（个人信息保护法）→ R001
   - GDPR → R002
   - 网络安全法 → R003
   - 数据安全法 → R004
5. 输出风险等级 + 整改建议

## 边界情况

- 高风险合规问题 → 必须触发 `risk_approval` 流程（人工审批）
- 用户提供合同标题而非 ID → 先 search_contracts 找到 ID
- 跨多个法规 → 分多次 check_compliance 输出

## 输出模板

```
## 合同 / 法规概览
- ...

## 合规检查
- 法规 1: 风险等级 / 差距
- 法规 2: ...

## 整改建议
- ...
```

## 高风险提示

任何 risk=high 的检查结果都必须：
1. 立即在回答顶部加 ⚠️ 风险提示
2. 建议联系法务部门
3. 不自动推进到 finalize 阶段
