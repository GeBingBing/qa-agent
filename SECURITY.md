# Security Policy

## 报告漏洞

如果你发现安全问题，请**不要**直接提 issue。请：

1. 通过仓库的 **GitHub Security Advisories**（Repository → Security → Advisories → Report a vulnerability）私下提交报告
2. 或发送邮件到维护者邮箱（见 `pyproject.toml` authors 字段）

我们会在 **3 个工作日内** 给出初步回复，并在确认后协调披露时间表。

## 受支持的版本

当前仓库在 `main` 分支处于活跃开发阶段，仅维护 `main` 的最新 commit。
未发布稳定版本前，不对历史 tag 提供独立的安全补丁。

## 处理 LLM Provider API 凭据

`.env` 已加入 `.gitignore`。请遵守：

- **永远不要** commit `.env` / `.env.local` / `.env.*.local` 等带真实凭据的文件
- CI 中通过 `gitleaks` 扫描提交历史里的疑似 token
- 部署前轮换所有 `*_API_KEY`；生产环境推荐使用密钥管理系统（AWS Secrets Manager、HashiCorp Vault、GCP Secret Manager 等）

## 受影响数据范围

- `.traces/*.jsonl` 默认包含截断后的 query 与执行结果。`observability/redact.py` 会剥离 `<think>` 块、屏蔽 `sk-*` / `Bearer` token、超长截断。建议生产部署：
  - 设置 `KB_QA_TRACE_DIR` 到独立目录
  - 配置 logrotate / k8s sidecar 做日志轮转
  - 不要把 trace 目录暴露给 web

## 鉴权 / 网络

- `/v1/chat` 默认在生产环境必须设置 `KB_QA_API_TOKEN`（Bearer 鉴权）；未设置则视为 dev 模式放行
- `/health` `/metrics` 设计为公开端点，但生产建议通过 nginx / k8s NetworkPolicy 限制 `/metrics` 仅集群内可达
- CORS 通配 `*` 与 `allow_credentials` 不会同时启用（参见 `build_cors_kwargs`）

## 沙盒与工具

`core/sandbox.py` 是受限 bash 沙盒，**不是** 生产级隔离手段。生产请使用容器 / VM 级别的真正沙盒（如 gVisor、Firecracker）。
