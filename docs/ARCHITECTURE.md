# 架构说明（Architecture）

> 本文档描述 kb-qa-agent 的模块拓扑、数据流、关键设计决策。

## 系统拓扑

```
        ┌──────────────────────────────┐
        │   Frontend (React + Vite)    │
        │   - ChatPanel / Streaming    │
        │   - TracePanel / PlanView    │
        │   - Zustand + TanStack Query │
        └──────────┬───────────────────┘
                   │ HTTP + SSE
                   │ (Vite proxy /v1 → :8000)
        ┌──────────▼───────────────────┐
        │  FastAPI (main.py)           │
        │  - /health /v1/tools /v1/skills
        │  - POST /v1/chat (SSE)       │
        └──────────┬───────────────────┘
                   │
   ┌───────────┬───┴────┬─────────────┬───────────┐
   │           │        │             │           │
┌──▼──┐   ┌────▼───┐ ┌──▼──────┐ ┌────▼────┐ ┌────▼────┐
│RAG  │   │Tools   │ │ Skills  │ │  MCP    │ │ Sandbox │
│Chr  │   │Reg+Dom │ │ Loader  │ │ Clients │ │ (12)    │
└─────┘   └───┬────┘ └────┬────┘ └────┬────┘ └─────────┘
              │            │           │
       ┌──────▼────────────▼───────────▼──────────┐
       │     core/  (Flow + ReAct + DAG + Router) │
       └────────────────┬─────────────────────────┘
                        │
            ┌───────────▼──────────────┐
            │  Provider Adapter Layer  │
            │  7 BaseProvider 实例     │
            └────────────┬─────────────┘
                         │
              ┌──────────▼──────────┐
              │ 7 LLM Provider APIs │
              │ (Anthropic / OpenAI │
              │  compat × 6)        │
              └─────────────────────┘

       ┌────────────────────────────────┐
       │  observability/                 │
       │  - tracer (span JSONL)          │
       │  - cost (per-provider USD)      │
       │  - eval (recall + forbidden)    │
       └─────────────────────────────────┘
```

## 数据流（一次 `/v1/chat` 请求的完整旅程）

```
1. Frontend POST /v1/chat
   └─ body: {query, conversation_history, ...}

2. FastAPI api/chat.py:_stream_chat()
   └─ yield SSE: {"event":"start","data":{...}}

3. flows/intake.classify_intent()
   └─ Provider.structured(messages, ROUTER_SCHEMA)
   └─ yield SSE: {"event":"intake","data":{domain,intent,...}}

4. flows/plan_gen.generate_plan()
   ├─ RAG.retrieve(query, top_k=4)
   ├─ skill_loader.load_decision_cards() + apply_trust_gate() + select_by_model()
   ├─ planner.plan_with_retry() → DAG
   └─ yield SSE: {"event":"plan","data":{rationale,nodes,...}}

5. flows/dep_executor.execute_plan(plan)
   ├─ topological_order()  ← Kahn 算法
   ├─ 逐节点执行：
   │   - kind=tool  → ToolRegistry.execute(id, **args)
   │   - kind=llm   → Provider.chat()
   │   - kind=human → placeholder
   └─ yield SSE: {"event":"step_result","data":{...}}

6. flows/risk_approval.assess_and_route_risk()
   └─ Provider.structured(RISK_SCHEMA)
   └─ yield SSE: {"event":"risk","data":{risk_level,auto_proceed,...}}

7. 若 auto_proceed OR risk != high:
   flows/reflection.finalize_with_reflection()
   └─ reflect_and_revise() ≤ 2 轮
   └─ yield SSE: {"event":"final","data":{final_answer,...}}
   否则:
   └─ yield "blocked by risk"

8. Tracer 同步记录每个 span 到 .traces/{date}.jsonl
9. Cost 累计 token + USD 到 .cost/report.json
```

## 关键设计决策

### 1. 为什么在 Agently 之外再加一层 Provider Adapter？

Agently 4.x 的 settings 是全局单例，`Agently.set_settings("OpenAICompatible", {...})` 一次只能注入一组配置，热切换 Provider 不友好。

**本项目做法**：
- 业务层**不**直接用 `Agently.create_agent()` 调模型，而是走 `kb_qa_agent.providers` 适配层
- 适配层提供 `BaseProvider` 协议（chat / structured / stream / count_tokens / price_per_1k）
- Agently 仅在需要它内置的 MCP / Skills 执行器时才用，通过 `agently_adapter.py` 一次性注入 active provider
- 切换 Provider 只需改 `KB_QA_ACTIVE_PROVIDER` 环境变量，业务代码零修改

收益：
- 7 Provider 用同一套业务代码走通
- Provider 之间的协议差异（OpenAI 兼容 vs Anthropic）在适配层吸收
- 计费 / token 估算 / 流式输出统一接口

### 2. 为什么 mock MCP server 用 stdlib `http.server` 而不是 FastMCP？

- **零额外依赖**：FastMCP 在不同 Python 版本上有兼容问题；stdlib 始终可用
- **协议透明**：用户能直接看到 JSON-RPC over HTTP 的本质
- **docker-compose 友好**：不需要先 `pip install fastmcp` 才能起 server

JSON-RPC 协议层面与 MCP 完全兼容，客户端调 POST `/mcp` + `tools/list` / `tools/call`。

### 3. 为什么 Skills 写成 markdown 而不是 Python 类？

- markdown + frontmatter 适合放进 git，跟随业务变化而演进
- Python 类则会跟代码耦合，改 Skill 要发版
- 渐进披露：触发时只看 frontmatter（DecisionCard），实际执行时才读 body / references

`core/skill_loader.py` 在运行时把 markdown 解析成 `DecisionCard`（in-memory dataclass），供选择 / 信任门 / 注入 Plan 使用。

### 4. 为什么 reflection 默认只跑 2 轮？

- 1 轮：明显低质量回答（recall < 0.5）会被打回
- 2 轮：通常能纠错 + 提分；再增加轮数边际收益下降
- 可在 `flows/reflection.py:finalize_with_reflection(max_rounds=...)` 调整

### 5. 为什么 TracePanel 在前端而不是后端？

- 调试 agent 行为时，前端实时可视化比 CLI 友好得多
- Trace 数据已经在 SSE 流里推了，前端只是把它"画"出来
- 不影响后端性能（只在 yield 时附带状态）

### 6. 为什么用 ChromaDB 而不是 FAISS / Qdrant？

- 持久化开箱即用（`PersistentClient(path=...)`）
- 内置多种 embedding function（local sentence-transformers / OpenAI / DashScope）
- HTTP 服务模式 + Python 客户端模式两种都支持，docker-compose 里跑 server 模式
- 比 FAISS 更适合中等规模数据 + 元数据过滤

## 模块依赖图（简化）

```
providers/       ← 最底层，无依赖
   ↓
core/            ← 依赖 providers/
   ↓
domains/         ← 依赖 core/（用 ToolRegistry）
   ↓
flows/           ← 依赖 core/ + domains/
   ↓
api/             ← 依赖 flows/ + core/
observability/   ← 独立，可被任何层使用
```

## 性能特征（典型值）

| 阶段 | 耗时 | 说明 |
|---|---|---|
| `classify_intent` | 0.5 - 2s   | 一次 LLM structured 调用 |
| `plan_with_retry` | 1 - 5s      | 1 - 3 次 LLM 调用（含重试）|
| `execute_plan`    | 2 - 10s     | 取决于 tool 调用次数 |
| `assess_risk`     | 1 - 3s      | 一次 LLM structured |
| `reflect`         | 2 - 8s      | 1 - 2 轮 evaluate + revise |
| **端到端**        | **6 - 28s** | 取决于 Provider 响应速度 |

## 可观测性体系

### Tracer

每次 `/v1/chat` 请求生成多个嵌套 span：

```
chat_request (root)
├── intake             (~1s)
├── plan_gen           (~3s)
├── exec_node × N      (~2s each)
├── risk_assessment    (~2s)
└── reflection_finalize (~5s)
```

落盘为 `.traces/{YYYY-MM-DD}.jsonl`，每行一个 span，含 `span_id` / `parent_id` / `start_ms` / `duration_ms` / `attrs` / `error`。

### Cost

每次 LLM 调用后立即记录 `CostEntry(provider, model, input_tokens, output_tokens, cost_usd)`。
`get_report()` 返回按 provider 聚合的 `CostReport`：
- `total_usd`
- `total_input_tokens` / `total_output_tokens`
- `by_provider`（每家 USD / token / 调用次数）

### Eval

`run_eval.py` 跑完整 `golden_qa.jsonl`，每题：
- 调 `/v1/chat`，等 final 事件
- 用 `score_answer()` 检查关键词 recall ≥ 0.7
- 检查 `expected_domain` / `expected_risk` 是否匹配
- 检查 `forbidden_phrases` 是否未出现

最后输出通过率、平均 recall、平均延迟、总 cost。

## 安全边界

| 层级 | 措施 |
|---|---|
| **Provider** | API key 在 `.env`，`.gitignore` 已配置；Agently settings 不落盘 |
| **Sandbox** | 命令前缀白名单 + `asyncio.wait_for` 超时 + 工作目录隔离 + `HOME` 重置 |
| **Skills** | trust_level 三级（trusted / review / blocked），第三方默认 blocked |
| **Risk Gate** | 模型评估高风险操作（合规 / 大额金钱 / 跨境数据），自动转人工 |
| **MCP** | 内部 mock server 只读；外部 MCP 通过 URL 配置，不持久化凭证 |

## 扩展方向

| 方向 | 大致路径 |
|---|---|
| **并行执行** | `dep_executor` 改成"按层并发"——每层节点用 `asyncio.gather` |
| **持久化记忆** | 在 `core/` 加 `memory.py`，会话级存到 SQLite / Redis |
| **多模态输入** | 在 `api/chat.py` 加图片 / PDF 处理；调 Provider 的 vision endpoint |
| **A/B 测试** | `run_eval.py` 支持 `--providers deepseek,opus,glm` 多 provider 对比 |
| **更细权限** | 在 `tool_registry` 上加 RBAC（按 role 限可见工具集）|
| **OpenTelemetry** | `tracer.py` 已留扩展位，接 OTLP exporter 即可上 Jaeger / Tempo |
