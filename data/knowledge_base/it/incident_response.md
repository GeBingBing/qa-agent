---
title: 工单与系统状态
domain: it
source_url: https://intranet.example.com/it/incident-response
last_updated: 2026-05-30
keywords: [工单, SLA, 系统状态, internal_wiki, operational, degraded, resolved]
---

# 工单与系统状态

## 工单系统

公司使用统一的 IT 服务台（Service Desk）管理所有内部 IT 请求。
工单编号格式：`T<6 位数字>`，例如 `T000001`。

### 工单类型

| 类型 | 处理 SLA | 示例 |
|---|---|---|
| 紧急（P0） | 30 分钟内响应，4 小时内修复 | 全员无法登录 / 生产事故 |
| 高（P1） | 1 工作日内响应，3 工作日内修复 | VPN 不通 / 邮箱异常 |
| 中（P2） | 2 工作日内响应 | 软件安装 / 权限申请 |
| 低（P3） | 5 工作日内响应 | 设备外设 / 一般咨询 |

### 工单状态

| 状态 | 说明 |
|---|---|
| `open` | 已创建，等待分派 |
| `in_progress` | 处理人已认领 |
| `pending_user` | 等待提交人补充信息 |
| `resolved` | 已解决，等待提交人确认 |
| `closed` | 提交人已确认或自动关闭 |

> 工单 `resolved` 后 3 个工作日内未确认将自动转 `closed`。

## 系统状态页

公司维护内部状态页（http://status.intranet.example.com），实时显示核心系统状态。

### 状态分级

| 级别 | 颜色 | 含义 |
|---|---|---|
| `operational` | 🟢 绿 | 正常 |
| `degraded` | 🟡 黄 | 部分功能异常 / 性能下降 |
| `partial_outage` | 🟠 橙 | 部分用户 / 功能不可用 |
| `major_outage` | 🔴 红 | 全员不可用 |

### 监控范围

| 系统 | 当前状态 | 备注 |
|---|---|---|
| 内部 Wiki (`internal_wiki`) | `operational` | 节假日维护窗口除外 |
| VPN 网关 | `operational` | |
| 邮件系统 | `operational` | |
| HR 系统 | `operational` | |
| 财务 OA | `degraded` | 已知问题：导出 PDF 慢，工单 T000456 |
| 监控平台 | `operational` | |

> 系统状态由 SRE 自动 + 手动双轨更新；状态变化会触发 IM 通知 + 邮件预警。

## 常见问题

### 我的工单 T001 处理到哪一步了？

可以在 IT 服务台输入工单编号查询；或访问个人工单中心。
**T001 的当前状态：`open`**（等待分派给 VPN 团队，VPN 域故障告警相关）。

### T003 是否已经解决？

**T003 状态：`resolved`**（处理人已修复，等待提交人确认；3 个工作日后自动关闭）。

### 内部 Wiki 现在能访问吗？

可以。`internal_wiki` 当前状态为 `operational`，无已知故障。
