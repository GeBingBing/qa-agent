# 生产化改进路线图（IMPROVEMENT_ROADMAP）

本文档承载从「能跑通的骨架」走到「可生产部署」的全部改造任务。
按 P0 → P3 分批落地；每个阶段都给出**变更点 / 关键文件 / 验收标准**。

> 状态约定：⏳ 未开始 · 🚧 进行中 · ✅ 已完成 · ❌ 已废弃

---

## 范围

聚焦四类问题：

1. 正确性硬伤（P0）
2. 流式 & 性能（P1）
3. 安全 & 可观测（P2）
4. 前端 + 工程化（P3）

不在本路线图：多租户计费、ChromaDB 集群化、完整 i18n、批量 RAG 数据治理工作流。

---

## P0 — 正确性硬伤

| # | 状态 | 改动 | 关键文件 |
|---|---|---|---|
| P0-1 | ✅ | 去掉 async 路径里的 `asyncio.run`；新增 `aexecute_plan` 异步入口 | `backend/kb_qa_agent/flows/dep_executor.py` |
| P0-2 | ✅ | DAG 单步 break 修正、清理 dead import；逐节点 step_start/step_result | `backend/kb_qa_agent/api/chat.py` |
| P0-3 | ✅ | `_extract_draft` 兜底（content/observation 同时识别） | `backend/kb_qa_agent/api/chat.py` |
| P0-4 | ✅ | `supports_response_formats()` 真实按 provider 名生效 | `backend/kb_qa_agent/providers/openai_compat.py` |
| P0-5 | ✅ | structured 思考块兜底 + 顶层 `{...}` 抽取 | `backend/kb_qa_agent/providers/structured.py` |
| P0-6 | ✅ | `provider`/`model` 请求级覆盖真实生效（`request_provider` ContextVar） | `backend/kb_qa_agent/api/chat.py`、`core/model_request.py` |
| P0-7 | ✅ | SSE 异常落 `error` 事件 + final 兜底 | `backend/kb_qa_agent/api/chat.py` |
| P0-8 | ✅ | 抽 `providers/env_keys.py`，统一 env 变量映射 | `backend/kb_qa_agent/providers/{env_keys,openai_compat,agently_adapter}.py` |

**验收**：
- `pytest backend/tests/ -v` 全绿
- 新增 `backend/tests/test_api_chat.py` 用 `TestClient` 跑一遍 SSE，断言事件顺序、`error` 兜底、`final.final_answer` 非空
- `eval/run_eval --limit 5` 通过率 ≥ 当前基线

---

## P1 — 流式 & 性能

| # | 状态 | 改动 | 关键文件 |
|---|---|---|---|
| P1-1 | ✅ | 真 LLM 流式 + thinking/answer 分流（`enable_reflection=False` 走 `provider.stream` + `<think>` 拆分） | `backend/kb_qa_agent/api/chat.py`、`core/model_request.py` |
| P1-2 | ✅ | `aexecute_plan` 异步 DAG 执行（已在 P0-1 完成） | `backend/kb_qa_agent/flows/dep_executor.py` |
| P1-3 | ✅ | RAG / Provider client 资源复用（lifespan 单例 + sync/async client cache） | `backend/kb_qa_agent/main.py`、`providers/openai_compat.py`、`api/chat.py` |
| P1-4 | ✅ | 客户端断开取消（`request.is_disconnected()` 检查点） | `backend/kb_qa_agent/api/chat.py` |
| P1-5 | ✅ | 前端 AbortController + Stop 按钮（streamChat 接收 signal；Send/Stop 共用按钮） | `frontend/src/lib/api.ts`、`hooks/useChatStream.ts`、`components/ChatPanel.tsx` |
| P1-6 | ✅ | 流式增量 ReactMarkdown + memo（TracePanel/PlanView/SkillList/ThinkingPanel 全部 memo） | `frontend/src/components/{ChatPanel,TracePanel,PlanView,SkillList,ThinkingPanel}.tsx` |

**验收**：
- 首字节 ≤ 1.5s（minimax-m2.7 简单问题）
- 关闭浏览器标签后 1s 内后端日志显示停止生成
- 前端 Stop 按钮在 streaming 状态可见且可立即中断
- bundle 不显著增大

---

## P2 — 安全 & 可观测

| # | 状态 | 改动 | 关键文件 |
|---|---|---|---|
| P2-1 | ✅ | API Bearer 鉴权（`KB_QA_API_TOKEN`，未设置则放行；端点公开 `/health` `/metrics`） | `backend/kb_qa_agent/api/{security,chat}.py`、`main.py` |
| P2-2 | ✅ | CORS 收紧；`build_cors_kwargs` 安全默认值（拒绝 `*` + credentials 并存，空列表 fallback 到 localhost:5173） | `backend/kb_qa_agent/main.py` |
| P2-3 | ✅ | request_id 中间件 + JSON 行日志（`KB_QA_LOG_JSON=1` 启用；ContextVar 串联 logger/tracer） | `backend/kb_qa_agent/observability/{logging_setup,request_id_middleware}.py` |
| P2-4 | ✅ | trace PII 屏蔽（`redact.py`：剥离 `<think>`、屏蔽 sk-*、Bearer token、超长截断） | `backend/kb_qa_agent/observability/{redact,tracer}.py` |
| P2-5 | ✅ | `/metrics` Prometheus + `/health/ready` 真实探测 | `backend/kb_qa_agent/{observability/metrics.py,api/health.py}` |
| P2-6 | ✅ | 可选 OTel exporter — `OTEL_EXPORTER_OTLP_ENDPOINT` 设置时 lifespan 自动注册 TracerProvider + BatchSpanProcessor + OTLPSpanExporter；SDK 缺失则降级 + warning | `backend/kb_qa_agent/observability/otel.py`、`main.py`、`.env.example` |
| P2-7 | ✅ | 测试补齐：cost / reflection / cors / security / metrics / redact / request_id 七套新测试 | `backend/tests/test_*.py` |
| P2-8 | ✅ | golden_qa 新增 q021/q022/q023 三条 `expected_risk=high` | `backend/eval/golden_qa.jsonl` |

**验收**：
- 未带 token 的 `/v1/chat` 请求返回 401（生产模式）
- `pytest --cov=kb_qa_agent` 核心模块行覆盖 ≥ 70%（再向 80% 推进）
- `curl /metrics` 返回 Prometheus 文本，包含 `kb_qa_chat_requests_total`
- `curl /health/ready` 在 Chroma/MCP 关闭时返回 503

---

## P3 — 前端 + 工程化

| # | 状态 | 改动 | 关键文件 |
|---|---|---|---|
| P3-1 | ✅ | ErrorBoundary + 全局 Toast；网络错误不再硬塞到对话气泡 | `frontend/src/components/{ErrorBoundary,Toast}.tsx`、`main.tsx`、`hooks/useChatStream.ts` |
| P3-2 | ✅ | 复制 / 重新生成 / 编辑回填（消息 hover 操作条） | `frontend/src/components/{MessageActions,ChatPanel}.tsx` |
| P3-3 | ✅ | textarea + Shift+Enter 换行 / Enter 发送 / 清空二次确认 / aria-live | `frontend/src/components/ChatPanel.tsx` |
| P3-4 | ✅ | `VITE_API_BASE` 配置化 + `.env.example` | `frontend/src/lib/{config,api}.ts`、`components/Sidebar.tsx`、`tsconfig.json`、`.env.example` |
| P3-5 | ✅ | 会话持久化（zustand `persist` + localStorage，仅持久化 messages） | `frontend/src/hooks/useStore.ts` |
| P3-6 | ✅ | `crypto.randomUUID` 生成消息 id（含降级） | `frontend/src/hooks/useStore.ts` |
| P3-7 | ✅ | 后端 Dockerfile（多阶段 uv + python:3.11-slim） | `backend/Dockerfile`、`docker-compose.yml`、`.dockerignore` |
| P3-8 | ✅ | 前端 Dockerfile（node:24-alpine 构建 + nginx:1.27-alpine 静态服务） | `frontend/{Dockerfile,nginx.conf,.dockerignore}` |
| P3-9 | ✅ | mock-mcp Dockerfile（纯 stdlib，build context 改成 backend/） | `backend/mock_mcp_servers/Dockerfile`、`docker-compose.yml` |
| P3-10 | ✅ | GitHub Actions CI（ruff + pytest + eslint + tsc + vite build + gitleaks） | `.github/workflows/ci.yml` |
| P3-11 | ✅ | `LICENSE` (MIT) + `CHANGELOG.md` + `SECURITY.md` | 仓库根 |
| P3-12 | ✅ | 删除 `frontend/package-lock.json`，保留 pnpm 单一锁 | `frontend/package-lock.json`（已删） |
| P3-13 | ✅ | 嵌入模型缓存目录（`KB_QA_HF_HOME` / `HF_HOME` / `SENTENCE_TRANSFORMERS_HOME`） | `backend/kb_qa_agent/core/rag.py`、`docker-compose.yml`（`HF_HOME=/data/hf-cache`） |

**验收**：
- `docker compose up --build` 一键拉起 chromadb + mock-mcp + app + web
- GitHub Actions 阻断 lint/test 失败
- `frontend/.env.production` 设置后产物访问 `${VITE_API_BASE}` 生效
- 仓库根存在 `LICENSE`，README/license 文档一致

---

## 关联文档

- `specs/chat.spec.md` — `/v1/chat` SSE 协议规范（P0 锁协议）
- `specs/observability.spec.md` — trace / cost / metrics 协议规范（P2 锁协议）
- `specs/providers.spec.md` — 7 Provider 适配层规范（P0 在 _supports_json_mode / structured 修订时同步）
- `docs/CODE_MAP.md` — 模块索引（每阶段新增模块需同步索引）
- `CLAUDE.md` — 项目级 Claude Code 记忆，常见陷阱与工作流约定

## 落地节奏

1. P0 一组小 PR，每个 fix 一个 commit
2. P1 真流式 + 资源复用 + 前端 abort
3. P2 安全 + 可观测，配合 `chat.spec.md` / `observability.spec.md` 新规范
4. P3 工程化，CI 上线后补 LICENSE/CHANGELOG/SECURITY 一并合入
