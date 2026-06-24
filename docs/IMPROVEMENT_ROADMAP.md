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

## P4 — RAG 切分 / 引用 / 摄取幂等

聚焦三个问题：
1. 字符级切分丢上下文（不知道当前段属于哪个章节）
2. 同一份政策文档重复写入 → chunk 数翻倍
3. 模型拿到 RAG 片段但回答里不引用，前端看不到来源

| # | 状态 | 改动 | 关键文件 |
|---|---|---|---|
| P4-1 | ✅ | markdown-aware 切分器（`ChunkPiece` + heading_path；H1/H2/H3 + code fence 保留 + 超长 sliding window） | `backend/kb_qa_agent/core/chunking.py` |
| P4-2 | ✅ | `RAG.add_documents` 改走 `chunk_markdown`；id = `sha1(source+text+chunk)`；metadata 写入 `heading_path/doc_hash/ingested_at/embedding_model/embedding_provider` | `backend/kb_qa_agent/core/rag.py` |
| P4-3 | ✅ | `eval/bootstrap_kb` 重写：递归 rglob、frontmatter 解析、`--reset` / `--json` 标志、`new/updated/skipped/chunks_added` 真实统计 | `backend/eval/bootstrap_kb.py`、`eval/__init__.py` |
| P4-4 | ✅ | 幂等摄取：同 source 二次写入先 `delete(where={source})` 后 add，chunk 总量恒定 | `backend/kb_qa_agent/core/rag.py` |
| P4-5 | ✅ | `sources` SSE 事件：plan 之后、answer_delta 之前发；按 source 去重；保留 score 最低那条；`snippet ≤ 240` 字 | `backend/kb_qa_agent/api/chat.py:_build_sources_event()` |
| P4-6 | ✅ | 真流式 prompt 注入：system prompt 强制 `[i]` 角标 + 末尾「## 参考资料」段；`MAX_RAG_HITS_INTO_PROMPT = 4` | `backend/kb_qa_agent/api/chat.py:_real_stream_answer()` |
| P4-7 | ✅ | `specs/chunking.spec.md` 新增；`specs/chat.spec.md` §4/§5/§6 加入 `sources` 事件契约 | `specs/{chunking,chat}.spec.md` |
| P4-8 | 🚧 | 前端 sources chip 渲染（计划在 P4-frontend 批做） | `frontend/src/components/ChatPanel.tsx`、`hooks/useChatStream.ts`、`types/chat.ts` |
| P4-9 | ✅ | 真实政策文档 10 份入仓（hr×2 / finance×2 / it×2 / legal×3）；`data/knowledge_base/` 提交策略写进 CLAUDE.md | `data/knowledge_base/`、`CLAUDE.md` |
| P4-10 | ✅ | 测试：3 套新测试（`test_chunking` / `test_ingest_idempotent` / `test_chat_with_citations`）共 414 行 | `backend/tests/test_*.py` |

**验收**：
- 同 source 二次 `add_documents()` → collection 中 chunk 总量恒定（`test_same_doc_re_ingest_does_not_grow`）
- 改 source 内容 → 旧 chunk 全部清理（`test_changed_content_replaces_old_chunks`）
- 切片携带 `heading_path`，检索 hit 的 metadata 可还原 `[i] source#heading`（`test_metadata_includes_heading_path_and_doc_hash`）
- `_real_stream_answer` 的 user_prompt 包含「政策片段」段 + 角标规则（`test_rag_hits_inject_into_real_stream_prompt`）
- `eval/bootstrap_kb` 输出 `files=new/updated/skipped/chunks_added` 四件套

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
