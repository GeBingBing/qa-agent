---
name: hr-policy-review
description: 当用户询问人事相关政策（请假 / 考勤 / 薪酬 / 合同 / 离职）时调用。组合 query_leave_balance / query_leave_history / query_attendance_policy 三个内部工具，并参考 references/leave-checklist.md 输出结构化回答。
metadata:
  version: 1.0
  domain: hr
  install_source: builtin
  trust_level: trusted
  keywords:
    - 请假
    - 年假
    - 病假
    - 考勤
    - 假期
    - leave
    - vacation
    - attendance
allowed-tools:
  - svc:query_leave_balance
  - svc:query_leave_history
  - svc:query_attendance_policy
---

# HR Policy Review Skill

回答人事域问题。流程：

1. 调用 `query_leave_balance(employee_id)` 拿到余额（如果用户给了 employee_id）
2. 调用 `query_leave_history(employee_id, limit=5)` 拿到最近申请
3. 调用 `query_attendance_policy()` 拿到制度要点
4. 综合输出回答，要求：
   - 先直接回答用户问题
   - 再补充"申请流程 / 注意事项"
   - 引用具体制度条款
   - 风险点（如年假余额不足）显式提示
   - 不要重复工具调用已经返回的字段
5. 引用 references/leave-checklist.md 中的检查清单

## 边界情况

- 用户没有提供 employee_id → 先问 employee_id，不要瞎猜
- 用户问"下个月年假" → 需要在回答里说明"按制度需提前 N 天申请"
- 余额不足 → 提示走"无薪假"或调整日期

## 输出模板

```
## 直接回答
...

## 申请流程
1. ...
2. ...

## 注意事项
- ...
```
