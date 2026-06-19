---
name: finance-approval-check
description: 当用户询问报销 / 预算 / 付款规则时调用。组合 query_expense_policy / query_department_budget / query_payment_status 三个内部工具，输出含"上限 / 审批阈值 / 当前预算余额"的合规建议。
metadata:
  version: 1.0
  domain: finance
  install_source: builtin
  trust_level: trusted
  keywords:
    - 报销
    - 预算
    - 付款
    - 差旅
    - 餐饮
    - 办公用品
    - expense
    - reimbursement
    - budget
allowed-tools:
  - svc:query_expense_policy
  - svc:query_department_budget
  - svc:query_payment_status
---

# Finance Approval Check Skill

回答财务域问题。流程：

1. 识别费用类别（差旅 / 餐饮 / 办公用品 / 其他）
2. 调用 `query_expense_policy(category)` 拿到规则
3. （可选）调用 `query_department_budget(department)` 校验预算余额
4. （可选）调用 `query_payment_status(payment_id)` 查询付款状态
5. 综合输出：
   - 报销上限 / 单价 / 天数上限
   - 审批阈值（超过多少金额需要什么级别审批）
   - 当前预算剩余（如有 department）
   - 高风险项（超阈值 / 余额不足）显式红色提示

## 边界情况

- 用户没给部门 → 跳过预算查询
- 用户没给费用类别 → 先问类别
- 跨类别报销 → 拆分为多次提交
- 大额（≥ 10000）→ 必须法务 + 财务双签

## 输出模板

```
## 报销规则
- 类别: ...
- 单价上限: ...
- 审批阈值: ...

## 当前预算（如有）
- 部门: ...
- 年度剩余: ...

## 审批建议
- ...
```
