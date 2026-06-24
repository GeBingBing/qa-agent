---
title: 账号与权限申请
domain: it
source_url: https://intranet.example.com/it/account-access-policy
last_updated: 2026-05-25
keywords: [账号, 权限, 申请, AWS, readonly, admin, maintainer]
---

# 账号与权限申请

## 适用范围

本政策覆盖公司所有内部系统账号 / 第三方 SaaS 账号 / 云平台权限的申请、变更、回收。

## 权限分级

| 级别 | 含义 | 典型场景 |
|---|---|---|
| `readonly` | 只读访问 | 查询监控 / 审计 / 调试观察 |
| `developer` | 读 + 普通写 | 日常开发 / 自助配置变更 |
| `maintainer` | 读 + 写 + 配置 | 运维 / 上线 / 灰度发布 |
| `admin` | 全部权限（含安全 / 计费） | 极少数岗位（SRE Lead / IT 主管） |

> `admin` 权限属于**敏感权限**，原则上不开放给非 SRE / 非 IT 主管岗位。
> 即便是临时调试需求，也建议通过 `maintainer` + 临时白名单方式实现。

## 申请流程

1. 在 IT 服务台创建工单，选择「账号 / 权限申请」类型
2. 注明：
   - 系统名称（AWS / 内部 wiki / 监控平台 …）
   - 期望权限级别
   - 业务需求与预计时长
3. 直属经理初审
4. **敏感权限 (`admin`)** 需 IT 主管 + 安全负责人**联签审批**
5. 工单批准后由 SRE 在 1 个工作日内开通

## AWS 控制台权限

- 默认所有研发岗位获得 `readonly` 权限（含 CloudWatch 日志、监控）
- `developer` / `maintainer` 按服务粒度申请（例如「ECS 部署 maintainer」「S3 项目桶 developer」）
- **`admin` 权限**仅限 SRE 团队 + 1 位备份；申请需附 incident / 变更窗口编号
- AWS 账号使用必须开启 MFA；连续 30 天未登录自动降级为 `readonly`

## 离职 / 转岗

- 离职手续启动当日，IT 自动冻结所有账号
- 转岗：当事人需在新岗位生效前提交「权限变更」工单，原权限将被回收

## 审计

- 所有 `admin` / `maintainer` 操作记入操作审计日志
- 操作日志保留 **180 天**，季度抽样审查
- 涉及生产数据库 admin 操作必须有变更窗口工单关联

## 常见问题

### 我能不能申请 AWS 控制台只读权限？

可以。在 IT 服务台提工单选 `readonly`，直属经理审批后 1 个工作日内开通。

### 临时需要 admin 权限做一次升级，怎么办？

不建议直接申请 `admin`。可走以下方式之一：

1. 临时白名单：在 IT 工单里申请「临时 maintainer + 操作窗口（≤ 4h）」
2. 协同 SRE：由 SRE 持有 `admin` 协助执行，操作过程双人见证
3. 极端紧急情况：CTO / IT 主管授权（事后必须补提工单）
