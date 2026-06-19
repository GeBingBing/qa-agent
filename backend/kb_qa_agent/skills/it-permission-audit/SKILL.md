---
name: it-permission-audit
description: 当用户询问 IT 账号 / 权限 / 工单 / 系统状态时调用。组合 query_account_access / query_ticket_status / query_system_status 三个内部工具。
metadata:
  version: 1.0
  domain: it
  install_source: builtin
  trust_level: trusted
  keywords:
    - 账号
    - 权限
    - 工单
    - VPN
    - AWS
    - GitHub
    - ticket
    - account
    - permission
allowed-tools:
  - svc:query_account_access
  - svc:query_ticket_status
  - svc:query_system_status
---

# IT Permission Audit Skill

回答 IT 域问题。流程：

1. 识别是"权限查询"还是"工单状态"还是"系统状态"
2. 权限类：调用 `query_account_access(employee_id)`
3. 工单类：调用 `query_ticket_status(ticket_id)`
4. 系统类：调用 `query_system_status()`
5. 输出：
   - 当前权限快照
   - 风险项（admin / 长期未登录 / 高危权限未审计）
   - 工单 SLA / 优先级
   - 系统故障时的 workaround

## 边界情况

- 用户只说"我的权限" → 反问 employee_id
- 权限缺失 → 自动建议提交工单
- 系统降级 → 给出已知的 workaround

## 输出模板

```
## 当前状态
- ...

## 风险项
- ...

## 建议下一步
- ...
```
