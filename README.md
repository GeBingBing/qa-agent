# kb-qa-agent

> 企业知识库问答助手 —— 7 Provider × Agently × RAG × MCP × Skills × 沙盒 × 反思 × SSE 流式 的端到端 Agent 参考实现。
> 后端 167 + 4 个测试全绿，前端 typecheck + build 全绿，CI 与 docker-compose 一键就位。

[![ci](https://github.com/GeBingBing/qa-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/GeBingBing/qa-agent/actions/workflows/ci.yml)

## 这是什么

`kb-qa-agent` 把企业内部知识库问答场景下的核心能力串成一条可运行的流水线：

```
用户问题
  → 意图路由（hr / finance / it / legal / general）
  → RAG 检索政策文档 + Skills 选择（信任门）
  → LLM 生成执行 DAG（tool / llm / human 三类节点 + 拓扑校验）
  → 异步并行执行
  → 风险评估（low / medium / high）+ 人工审批路由
  → 反思迭代 ≤ 2 轮  ＿或＿  真 LLM 流式
  → SSE 推送（DeepSeek 风格三段式：思考 / 工具调用 / 最终回答）
```

支持 **7 家 LLM Provider**（DeepSeek / OpenAI / Claude Opus / Moonshot Kimi / 智谱 GLM / 通义 Qwen / MiniMax），切换无需改业务代码，单次请求也能 override。

## 核心特性

| 类别 | 能力 |
|---|---|
| **多 Provider** | 7 家适配层 + 单次请求 override + Agently 4.x 注入 |
| **真流式** | `enable_reflection=False` 走 `provider.stream()`；`<think>` 块即时分流到独立 SSE 信道 |
| **DAG 异步执行** | `aexecute_plan` 在事件循环里 await，工具节点用 `asyncio.to_thread` 隔离 |
| **RAG** | ChromaDB + 本地 sentence-transformers（`BAAI/bge-small-zh-v1.5`），缓存目录 `KB_QA_HF_HOME` 可挂卷 |
| **Skills** | `SKILL.md` frontmatter + 关键词预筛 + 模型精筛 + 信任门；自带 4 个业务 Skill + 6 个 [Agently-Skills](https://github.com/AgentEra/Agently-Skills) dev skill |
| **MCP** | 外部高德 MCP + 自建本地 mock MCP server（stdlib JSON-RPC，纯 stdlib 镜像可一键起） |
| **沙盒** | 命令前缀白名单 + 超时 + 工作目录 + HOME 隔离 |
| **风险路由** | 模型评估 + 必要时阻断 + 兜底审批理由 |
| **可观测性** | JSONL trace（自动 redact `<think>` / `sk-*` / `Bearer`）+ Prometheus `/metrics` + 可选 OTel exporter |
| **鉴权 / CORS** | `KB_QA_API_TOKEN` Bearer 鉴权；CORS 安全默认值（拒绝 `*`+credentials 并存） |
| **前端** | React 18 + Vite 5 + Tailwind 3；流式 markdown + 思考折叠面板 + 工具 spinner + Stop 按钮 + 复制 / 重发 / 编辑 + 会话持久化 |
| **CI** | GitHub Actions：ruff + pytest + tsc + vite build + gitleaks |

## 快速开始

### 路径 A：完整容器化（推荐第一次）

```bash
git clone git@github.com:GeBingBing/qa-agent.git && cd qa-agent
cp .env.example .env       # 至少填一个 *_API_KEY
docker compose --profile full up -d --build
# 等 30s ~ 1min（首次构建会装 Python 依赖 + 下载嵌入模型）
open http://localhost:5173
```

启动的服务：
- `chromadb` (8001) — 向量库
- `mock-internal-mcp` (8765) — HR / Finance / IT / Legal 4 域 mock MCP
- `app` (8000) — FastAPI 后端，`/health`、`/health/ready`、`/metrics`、`/v1/chat`
- `web` (5173) — Nginx 静态 + `/v1` `/health` 反代

### 路径 B：开发模式（host 跑后端 + 前端，docker 跑数据面）

```bash
cp .env.example .env

# 1. 数据面
docker compose up -d chromadb mock-internal-mcp

# 2. 后端
uv sync --extra dev --extra eval
uv run python -m eval.bootstrap_kb      # 可选：导入政策文档到 ChromaDB
uv run uvicorn kb_qa_agent.main:app --reload --port 8000

# 3. 前端
cd frontend
pnpm install
pnpm dev                                 # → http://localhost:5173
```

## 验证

### 健康检查

```bash
curl http://localhost:8000/health
# {"status":"ok","active_provider":"minimax","available_providers":[...],"total_tools":12,"skills_loaded":10}

curl http://localhost:8000/health/ready
# {"status":"ready","checks":{"active_provider":{"ok":true,...}}}

curl http://localhost:8000/metrics | head
# Prometheus exposition 格式：kb_qa_chat_requests_total / kb_qa_chat_latency_seconds / ...
```

### 端到端问答（curl + SSE）

```bash
curl -N -X POST http://localhost:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"query": "我下个月想休 5 天年假，需要什么流程？"}'
```

事件流（DeepSeek 风格）：

```
start → intake → plan
[step_start, step_result] × N
risk
[thinking_delta] × T          # 真流式时；反思路径无此事件
[answer_delta] × M
final
```

> 异常或客户端断开都会以 `error → final` 兜底，前端永远拿到完整流。

### 切换 Provider

```bash
# 进程级
KB_QA_ACTIVE_PROVIDER=opus uv run uvicorn kb_qa_agent.main:app --reload

# 单次请求级（不重启）
curl ... -d '{"query":"...", "provider":"opus", "model":"claude-opus-4-8"}'
```

### 评估套件

```bash
uv run python -m eval.run_eval --provider deepseek --model deepseek-chat
uv run python -m eval.run_eval --limit 5     # 快速冒烟
```

`backend/eval/golden_qa.jsonl` 共 23 题，含 3 条 `expected_risk=high` 用例覆盖审批阻断分支。

## 鉴权（生产）

```bash
export KB_QA_API_TOKEN=$(openssl rand -hex 24)
uv run uvicorn kb_qa_agent.main:app --port 8000

# 必须带 Bearer
curl -X POST http://localhost:8000/v1/chat \
  -H "Authorization: Bearer $KB_QA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"hi"}'
```

未设置时按 dev 模式放行；`/health` `/metrics` 始终公开（建议网络层限制 `/metrics` scrape 范围）。

## 可选：OpenTelemetry exporter

```bash
uv add opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
docker run -d --name jaeger -p 4318:4318 -p 16686:16686 jaegertracing/all-in-one

OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_SERVICE_NAME=kb-qa-agent \
  uv run uvicorn kb_qa_agent.main:app --port 8000
# 在 http://localhost:16686 查看 trace
```

未设置 `OTEL_EXPORTER_OTLP_ENDPOINT` 时 OTel 通路自动 no-op，trace 仍写本地 JSONL。

## 工程实践

本项目采用 **SDD + TDD** 双驱动，path：

```
specs/<module>.spec.md            ← 单一事实源
   ↓
backend/tests/test_<module>.py    ← 红 → 绿 → 重构
   ↓
backend/kb_qa_agent/<module>.py   ← 实现
```

跑测试：

```bash
uv run pytest backend/tests -q                  # 171 tests, ~10s
uv run pytest --cov=kb_qa_agent --cov-report=term
uv run ruff check backend
```

前端：

```bash
pnpm typecheck   # tsc --noEmit
pnpm build       # vite build
```

GitHub Actions（`.github/workflows/ci.yml`）每次 push / PR 跑 ruff + pytest + tsc + vite + gitleaks 五件套。

## 项目结构

```
kb-qa-agent/
├── backend/
│   ├── kb_qa_agent/
│   │   ├── providers/      # 7 Provider 适配 + env_keys 单一映射 + Agently bridge
│   │   ├── core/           # planner / executor / RAG / sandbox / skill_loader / model_request / react_loop / reflection
│   │   ├── domains/        # 4 域 12 工具，bootstrap 幂等
│   │   ├── skills/         # 4 业务 Skill + 6 Agently-Skills
│   │   ├── mcp_clients/    # 高德 + 本地 MCP 客户端
│   │   ├── flows/          # intake / plan_gen / dep_executor (a)execute_plan / risk_approval / reflection
│   │   ├── api/            # /v1/chat (SSE) / health / security
│   │   └── observability/  # tracer + cost + redact + logging_setup + request_id_middleware + metrics + otel
│   ├── mock_mcp_servers/   # 纯 stdlib mock MCP server (8765)
│   ├── eval/               # golden_qa.jsonl + run_eval + bootstrap_kb
│   └── tests/              # 171 个测试
├── frontend/               # React + Vite + TS + Tailwind
├── data/                   # 政策文档 + mock JSON + Chroma 持久化
├── docs/                   # ARCHITECTURE / CODE_MAP / IMPROVEMENT_ROADMAP / SDD / TDD / PROVIDER_SETUP
├── specs/                  # chat / observability / providers / planner / sandbox / tool_registry
├── .github/workflows/      # ci.yml
├── docker-compose.yml      # 默认 profile：chromadb + mock-mcp；--profile full 加 app + web
├── CLAUDE.md               # Claude Code 项目记忆
├── CHANGELOG.md
├── SECURITY.md
└── LICENSE                 # MIT
```

## 文档导航

| 我想知道… | 看这里 |
|---|---|
| 整体架构和决策 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 模块速查（要找某段代码在哪） | [`docs/CODE_MAP.md`](docs/CODE_MAP.md) |
| `/v1/chat` SSE 协议 | [`specs/chat.spec.md`](specs/chat.spec.md) |
| trace / cost / metrics 协议 | [`specs/observability.spec.md`](specs/observability.spec.md) |
| 7 Provider 配置 / 切换 / 故障排查 | [`docs/PROVIDER_SETUP.md`](docs/PROVIDER_SETUP.md) |
| 路线图（P0–P3 全部 ✅，含每条改动的关键文件） | [`docs/IMPROVEMENT_ROADMAP.md`](docs/IMPROVEMENT_ROADMAP.md) |
| 漏洞披露 / 凭据处理 | [`SECURITY.md`](SECURITY.md) |
| 变更记录 | [`CHANGELOG.md`](CHANGELOG.md) |

## License

MIT
