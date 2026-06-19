# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **后端**：`/v1/chat` SSE 协议正式化（事件序列、不变量、错误模式见 `specs/chat.spec.md`）
- **后端**：API Bearer 鉴权 (`KB_QA_API_TOKEN`)，未设置则放行；`/health` `/metrics` 公开
- **后端**：`/health/ready` 真实探测 active provider 可用性
- **后端**：`/metrics` Prometheus 端点（`kb_qa_chat_requests_total`、`kb_qa_chat_latency_seconds`、`kb_qa_llm_tokens_total` 等）
- **后端**：`X-Request-Id` 中间件 + JSON 行结构化日志（`KB_QA_LOG_JSON=1` 启用）
- **后端**：`observability/redact.py` —— trace / 日志 / 错误信息中的 `<think>` 块、`sk-*`、`Bearer` token 自动屏蔽
- **后端**：真 LLM 流式 + `<think>` 拆分，新增 `thinking_delta` SSE 事件（DeepSeek 风格三段式）
- **后端**：`flows/dep_executor.aexecute_plan` 异步 DAG 执行器；同步入口在已有 event loop 中明确报错
- **后端**：客户端断开自动取消 (`request.is_disconnected()` 检查点）
- **后端**：`request_provider(name, model)` 上下文管理器，支持 `/v1/chat` 请求级 provider/model 覆盖
- **后端**：RAG / OpenAI client 单例复用（lifespan 注入，避免每请求重建）
- **后端**：`providers/env_keys.py` 单一 env 变量映射；`OpenAICompatProvider.supports_response_formats()` 按 provider 选择是否注入 `response_format=json_object`
- **后端**：`providers/structured.py` 鲁棒 JSON 抽取（思考块剥离 / 顶层 `{...}` 抽取 / 围栏剥离 / 多 chunk 缓冲）
- **前端**：`<think>` 折叠面板（思考中 / 已完成）+ tool 步骤运行 spinner + 流式 markdown
- **前端**：AbortController + Stop 按钮，可中断生成
- **前端**：错误边界 + 全局 Toast；网络错误不再硬塞到对话气泡里
- **前端**：消息复制 / 助手重新生成 / 用户消息编辑回填
- **前端**：textarea + Enter 发送 / Shift+Enter 换行；清空对话二次确认；aria-live 区域
- **前端**：`VITE_API_BASE` 配置化；新增 `frontend/.env.example`
- **前端**：会话持久化（`localStorage` 通过 zustand `persist` 中间件）
- **前端**：消息 id 用 `crypto.randomUUID`
- **前端**：`TracePanel` / `PlanView` / `SkillList` / `ThinkingPanel` 全部 `React.memo`
- **工程化**：后端 / 前端 / mock-mcp 三个 Dockerfile + `.dockerignore`
- **工程化**：`docker-compose.yml` 加入 `app` / `web` 服务（`--profile full` 启用），所有服务带 healthcheck
- **工程化**：GitHub Actions CI（ruff + pytest + eslint + tsc + vite build + gitleaks 秘钥扫描）
- **工程化**：`LICENSE` (MIT) + `CHANGELOG.md` + `SECURITY.md`
- **文档**：`specs/chat.spec.md`、`specs/observability.spec.md`、`docs/IMPROVEMENT_ROADMAP.md`
- **测试**：新增 7 套测试套件（cors / security / redact / request_id / metrics_ready / cost / reflection / dep_executor / api_chat / env_keys / request_provider / rag_lifespan / thinking_split），共 167+ 用例
- **评估**：`golden_qa.jsonl` 新增 q021/q022/q023 三条 `expected_risk=high` 用例

### Changed
- **后端**：CORS 安全默认值 (`build_cors_kwargs`)：通配 `*` 与 `allow_credentials` 不再共存；空配置 fallback 到 `localhost:5173`
- **后端**：DAG 执行去掉单步 `break`，每个节点都发 `step_start` / `step_result`
- **后端**：`_extract_draft` 兜底：当无 LLM content 时回退到 tool observation

### Fixed
- **后端**：`asyncio.run` 嵌套在已运行 event loop 中导致的 `/v1/chat` RuntimeError
- **后端**：`<think>...</think>` 写入 trace JSONL 的 PII 泄露
- **后端**：`response_format=json_object` 对非 OpenAI 协议 provider 误注入
- **前端**：`step_result` 事件被静默丢弃（旧前端按 `{results: {...}}` 解析，新协议是 per-node 平铺）

