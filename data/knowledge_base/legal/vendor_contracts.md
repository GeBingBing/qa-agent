---
title: 主要供应商合同摘要
domain: legal
source_url: https://intranet.example.com/legal/vendor-contracts
last_updated: 2026-06-01
keywords: [AWS, JetBrains, GDPR, DPA, 合同, 跨境, PIPL]
---

# 主要供应商合同摘要

> 本文档是公司主要 SaaS / 云 / 工具类供应商的合同摘要。
> 完整文本由法务在合同管理系统中保存。

## AWS（Amazon Web Services）

### 服务范围

- 计算（EC2 / ECS / Lambda）
- 存储（S3 / EBS）
- 数据库（RDS / DynamoDB）
- 网络（VPC / CloudFront）
- 监控（CloudWatch）

### 合同要点

| 项 | 内容 |
|---|---|
| 主合同 | AWS Customer Agreement v2024.07 |
| **DPA** | AWS Data Processing Addendum，含 GDPR + PIPL 双合规附件 |
| 计费区域 | 同时使用「中国（宁夏）」与「Tokyo」两个 region |
| 跨境备案 | 国家网信办「标准合同」备案号 LCD-2025-008（仅限 Tokyo region） |
| 续签金额 | 2026 年度续签 1,200,000 元（含计算 / 存储 / 流量） |
| 续签审批 | 已通过 法务复核 + CFO + CEO（参考 `finance/payment_workflow.md` 阈值表） |
| SLA | 99.99%（计算）/ 99.95%（存储）|

### GDPR 合规

- 标准 SCC（最新版）已签署
- 子处理者列表更新通过 AWS 官方页面订阅
- 数据主体权利通过 AWS Service Health Dashboard + Support 工单组合处理
- 详见 `data_compliance.md` 中的「AWS 中国合同符合 GDPR 吗？」段

### 已知风险点

- AWS 中国（宁夏）与 Tokyo 双账号并存，跨账号资源调用必须明确数据流向
- 客户 SDK 默认走最近 region；东南亚客户实际写入 Tokyo，触发跨境，已通过 DPA + 备案覆盖
- 大额付款 ≥ 500,000 元，必须法务复核，不可由财务总监单独放行

## JetBrains

### 服务范围

- IntelliJ IDEA / PyCharm / WebStorm 等团队订阅
- TeamCity（CI/CD）
- 2025 年新增 Qodana（代码质量）

### 合同要点

| 项 | 内容 |
|---|---|
| 主合同 | JetBrains Toolbox All Pack v2025 |
| **DPA** | JetBrains Privacy Statement + DPA Addendum（GDPR / PIPL）|
| 订阅周期 | 年付，每年 1 月续签 |
| 当年金额 | 80,000 元（≤ 100,000 阈值，CFO 不必单独参与）|
| SLA | 标准（不保 Uptime）|
| 数据存储 | 学习行为数据存于 EU；可在 IDE 设置中关闭遥测 |

### 数据合规

- 默认开启的 telemetry 涉及代码 metadata（不含代码内容）出境到 EU
- 公司策略：在企业模板中**默认关闭** Send Usage Statistics
- 个别开发者可自愿开启用于 bug 反馈

## Google Workspace

| 项 | 内容 |
|---|---|
| 主合同 | Google Workspace Enterprise Agreement |
| DPA | Google Cloud Data Processing Addendum |
| 数据存储 | EU + US 多 region |
| 跨境备案 | 安全评估通过，编号 LCD-2024-014 |
| 当年金额 | 250,000 元 |

## Slack（企业 SSO）

| 项 | 内容 |
|---|---|
| 主合同 | Slack Enterprise Grid Agreement |
| DPA | 含 GDPR + CCPA 附件 |
| 数据存储 | US |
| 跨境备案 | 标准合同备案，编号 LCD-2025-002 |
| 当年金额 | 180,000 元 |

## OpenAI 海外 API

| 项 | 内容 |
|---|---|
| 主合同 | OpenAI Enterprise Agreement v2025 |
| **DPA** | OpenAI Data Processing Addendum（GDPR）|
| 数据出境 | prompt / completion 走脱敏，不含真实客户数据 |
| 跨境备案 | 标准合同备案，编号 LCD-2025-019 |
| 计费 | 按用量月结 |

## 待续签 / 高风险

| 供应商 | 到期日 | 风险点 |
|---|---|---|
| AWS | 2027-01-01 | 已续签 1,200,000 元，已审批 |
| Slack | 2026-12-31 | 跨境备案续期需要提前 60 天准备 |
| Google Workspace | 2027-03-31 | EU 子处理者列表本季度有更新，需复核 |

## 合同检索

- 法务保存所有原件 + 中文翻译
- 财务保存付款凭证
- 通过合同管理系统按供应商 / 域 / 关键词搜索
- DPA 模板见 `contract_template_dpa.md`
