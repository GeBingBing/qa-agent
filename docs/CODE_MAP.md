# 代码地图（Code Map）

> 内部模块索引 + 关键代码片段导览。本文档帮助快速定位某个能力的实现位置。

## 顶层目录

```
kb-qa-agent/
├── backend/
│   ├── kb_qa_agent/        Python 主包
│   ├── mock_mcp_servers/   FastMCP 自建服务器
│   └── eval/               评估脚本与黄金集
├── frontend/               React + Vite 前端
├── data/                   知识库文档 + mock JSON 数据
├── docs/                   架构 / Provider / 代码地图
├── docker-compose.yml      ChromaDB + mock MCP 服务编排
├── pyproject.toml          后端依赖与项目元信息
└── .env.example            7 Provider + MCP + RAG + 沙盒配置占位
```

## 后端模块导览

### `backend/kb_qa_agent/providers/` — Provider 适配层

| 文件 | 关键内容 |
|---|---|
| `base.py` | `BaseProvider` 协议（chat / structured / stream / count_tokens / price_per_1k）+ `ChatMessage` / `ChatResponse` / `StreamChunk` 数据类 |
| `openai_compat.py` | 6 家 OpenAI 兼容协议 Provider 通用实现（DeepSeek / OpenAI / Kimi / GLM / DashScope / MiniMax）|
| `claude.py` | Anthropic Claude / Opus 适配（system 拆分 / `messages.create` / `messages.stream`）|
| `structured.py` | Schema → system prompt 注入 + JSON 解析 + 顶层字段类型校验 |
| `registry.py` | `PROVIDER_REGISTRY`（7 实例）+ `get_provider` / `list_available` / `active_provider` + 默认定价表 |
| `agently_adapter.py` | 启动时把 active provider 注入 Agently 全局 settings |

### `backend/kb_qa_agent/core/` — 核心引擎

| 文件 | 关键 API | 说明 |
|---|---|---|
| `model_request.py` | `TaskExecutor.run_text` / `run_structured` / `astream_text`、`quick_text`、`quick_structured` | 单次请求 + Schema 输出封装 |
| `flow_engine.py` | `build_flow` / `chunk` / `to_sub_flow` / `build_llm_chunk` | TriggerFlow 工厂 + 子流契约 |
| `tool_registry.py` | `ToolRegistry.register` / `filter` / `to_prompt_blocks` / `execute`、`GLOBAL_REGISTRY` | 工具注册表（含 domain / side_effect_level）|
| `react_loop.py` | `ReActLoop.run` / `run_stream`、`REACT_SCHEMA` | ReAct 循环（含 Grace Call 预算降级）|
| `router.py` | `route_query` + `ROUTER_SCHEMA` | 4 域 + general 意图路由 |
| `planner.py` | `plan_dag` / `plan_with_retry` / `validate_plan` / `topological_order` | DAG 规划 + Kahn 拓扑 |
| `reflection.py` | `evaluate_draft` / `revise_draft` / `reflect_and_revise`、`DEFAULT_REPORT_CRITERIA` | Draft → Evaluate → Revise 循环 |
| `rag.py` | `RAG.add_documents` / `retrieve` / `format_hits`、`chunk_text` | ChromaDB 持久化 + 本地 embedding |
| `sandbox.py` | `BashSandbox.run`（命令前缀白名单 + `asyncio.wait_for` 超时）| 受控执行环境 |
| `skill_loader.py` | `load_decision_cards` / `select_by_model` / `select_required` / `apply_trust_gate` | Skills 加载 + 选择 + 信任门 |

### `backend/kb_qa_agent/domains/` — 4 域 12 工具

| 文件 | 工具列表 |
|---|---|
| `_common.py` | `load_mock(domain)` 带缓存的 mock 数据加载 |
| `hr/__init__.py` | `query_leave_balance` / `query_leave_history` / `query_attendance_policy` |
| `finance/__init__.py` | `query_expense_policy` / `query_department_budget` / `query_payment_status` |
| `it/__init__.py` | `query_account_access` / `query_ticket_status` / `query_system_status` |
| `legal/__init__.py` | `query_contract` / `search_contracts` / `check_compliance` |
| `__init__.py` | `bootstrap()` 一次性注册 12 工具到 `GLOBAL_REGISTRY`（幂等）|

### `backend/kb_qa_agent/skills/` — 4 个 Skills

| 目录 | 域 | 主要内容 |
|---|---|---|
| `hr-policy-review/` | hr | 假期 / 考勤 / 请假流程；含 `references/leave-checklist.md` |
| `finance-approval-check/` | finance | 报销规则 / 预算校验 / 审批阈值 |
| `it-permission-audit/` | it | 账号权限 / 工单 / 系统状态 |
| `legal-compliance-scan/` | legal | 合同条款 / 合规审查（PIPL / GDPR / 网络安全法 / 数据安全法）|
| `agently/` | dev-skill | Agently 框架入口路由（来自 [Agently-Skills](https://github.com/AgentEra/Agently-Skills)） |
| `agently-request/` | dev-skill | Agently 请求侧（model setup / prompt / output / KB） |
| `agently-runtime/` | dev-skill | Action Runtime / MCP / Execution Environment |
| `agently-dynamic-task/` | dev-skill | Dynamic Task DAG / TaskDAGExecutor |
| `agently-triggerflow/` | dev-skill | TriggerFlow 编排（branching / approvals / restart-safe） |
| `agently-migration/` | dev-skill | LangChain / LangGraph / LlamaIndex / CrewAI → Agently 迁移路径 |

每个 SKILL.md 包含 frontmatter（`name` / `description` / `metadata.{version,domain,trust_level,keywords}` / `allowed-tools`）+ workflow 描述 + 边界情况 + 输出模板。

### `backend/kb_qa_agent/mcp_clients/` — MCP 客户端

| 文件 | 用途 |
|---|---|
| `amap_client.py` | 外部高德地图 MCP 客户端（占位实现，便于不连真实服务也能跑端到端测试）|
| `internal_mcp_client.py` | 本地自建 MCP 客户端（HTTP + JSON-RPC）|

### `backend/kb_qa_agent/flows/` — 5 sub-flow 流水线

| 文件 | 入口函数 | 职责 |
|---|---|---|
| `intake.py` | `classify_intent` | 用户问题 → domain / intent / confidence |
| `plan_gen.py` | `generate_plan` | RAG 检索 + Skill 选择 + DAG 生成 |
| `dep_executor.py` | `execute_plan` | 拓扑顺序执行 tool / llm / human 节点 |
| `risk_approval.py` | `assess_and_route_risk` | 风险评估（low/medium/high）+ 审批路由 |
| `reflection.py` | `finalize_with_reflection` | Draft → Evaluate → Revise 循环 |

### `backend/kb_qa_agent/api/` — FastAPI 路由

| 文件 | 端点 |
|---|---|
| `health.py` | `GET /health`、`GET /v1/tools`、`GET /v1/skills` |
| `chat.py` | `POST /v1/chat`（SSE 流式）|
| `models.py` | Pydantic：`ChatRequest` / `StreamEvent` / `HealthResponse` |

### `backend/kb_qa_agent/observability/` — 可观测性

| 文件 | 提供 |
|---|---|
| `tracer.py` | `span` 上下文管理器；JSONL 落盘到 `.traces/{date}.jsonl` |
| `cost.py` | `CostEntry` / `CostReport` / `record` / `get_report` / `save_report_to_disk` |
| `eval.py` | `EvalSample` / `EvalResult` / `score_answer`（recall + 风险匹配 + forbidden 短语）|

### `backend/kb_qa_agent/main.py` — 应用入口

- 加载 `.env`（多路径回退）
- `lifespan` 钩子注入 active provider 到 Agently
- 注册 4 域工具
- 配置 CORS
- 挂载 `health` / `chat` 路由

### `backend/kb_qa_agent/SETTINGS.yaml`

- `${ENV.*}` 占位符；`config.py:_substitute_env` 在加载时解析
- 7 Provider × (api_key / base_url / default_model)
- MCP / RAG / 沙盒 / 可观测性 / API 配置分组

### `backend/kb_qa_agent/config.py`

- `get_config()` 单例，缓存解析后的配置
- `reset_config_cache()` 测试钩子
- `.env` 加载顺序:项目根 → backend → CWD → 自动搜索

### `backend/mock_mcp_servers/internal_systems_mcp.py`

- stdlib `http.server` 实现的 MCP-over-HTTP server
- 监听 `:8765`
- 暴露 12 个工具（与 4 域 `register()` 同步）
- JSON-RPC：`tools/list` / `tools/call`
- `GET /health` 用于 docker compose 健康检查

### `backend/eval/`

| 文件 | 用途 |
|---|---|
| `golden_qa.jsonl` | 20 题黄金问答集（4 域 + general），含 expected_keywords / expected_domain / expected_risk |
| `run_eval.py` | CLI 评估脚本：调 `/v1/chat` → 打分 → 写 `report_<provider>_<ts>.json` |
| `bootstrap_kb.py` | 把 `data/knowledge_base/{domain}/*.md` 灌入 ChromaDB |

## 前端模块导览

```
frontend/src/
├── main.tsx               入口（QueryClient + StrictMode）
├── App.tsx                Sidebar + ChatPanel 双栏布局
├── index.css              Tailwind + 暗色主题 CSS 变量
├── types/chat.ts          ChatMessage / Domain / RiskLevel / StreamEvent 类型
├── lib/
│   ├── api.ts             SSE 客户端（fetch + ReadableStream + 块解析）
│   └── utils.ts           cn() / formatDuration / formatCost
├── hooks/
│   ├── useStore.ts        Zustand 全局状态（messages / isStreaming）
│   └── useChatStream.ts   把 SSE 事件映射到 store
└── components/
    ├── ui/badge.tsx       6 variant Badge
    ├── ui/button.tsx      shadcn 风格 Button
    ├── ChatPanel.tsx      主对话区 + 输入框 + 流式滚动
    ├── Sidebar.tsx        服务状态面板
    ├── TracePanel.tsx     intake → plan → steps → risk → reflection 实时
    ├── PlanView.tsx       DAG 可视化（tool / llm / human 三色 + depends_on）
    ├── SkillList.tsx      命中 / 阻断 Skills
    └── DomainBadge.tsx    4 域 + 风险颜色映射
```

## 关联规范与路线图

| 文档 | 作用 |
|---|---|
| `docs/IMPROVEMENT_ROADMAP.md` | P0 → P3 生产化改进路线图（每条 todo 都对应仓库改动） |
| `specs/chat.spec.md` | `/v1/chat` SSE 协议规范（事件序列 / 不变量 / 错误模式） |
| `specs/observability.spec.md` | trace / cost / metrics / structured log 规范 |
| `specs/providers.spec.md` | 7 Provider 适配层规范 |
| `specs/planner.spec.md` | DAG 规划与拓扑排序规范 |
| `specs/sandbox.spec.md` | Bash 沙盒规范 |
| `specs/tool_registry.spec.md` | 工具注册表规范 |

## 关键代码片段索引

### 7 Provider 怎么统一

```python
# backend/kb_qa_agent/providers/base.py
@runtime_checkable
class BaseProvider(Protocol):
    name: str
    def available(self) -> bool: ...
    def chat(self, messages, *, model=None, ...) -> ChatResponse: ...
    def structured(self, messages, schema, ...) -> dict: ...
    def stream(self, messages, ...) -> AsyncIterator[StreamChunk]: ...
    def count_tokens(self, text, *, model=None) -> int: ...
    def price_per_1k(self, model, direction) -> float: ...
```

### DAG 拓扑排序（Kahn 算法）

```python
# backend/kb_qa_agent/core/planner.py:topological_order
in_degree = {n.id: 0 for n in plan.nodes}
children = {n.id: [] for n in plan.nodes}
for n in plan.nodes:
    for dep in n.depends_on:
        in_degree[n.id] += 1
        children[dep].append(n.id)
queue = [by_id[nid] for nid, d in in_degree.items() if d == 0]
# ... Kahn 标准实现
```

### ReAct Grace Call（预算耗尽时的优雅降级）

```python
# backend/kb_qa_agent/core/react_loop.py
if budget_left <= 1:
    extra_instruct = f"\n\n⚠️ 步骤预算只剩 {budget_left} 步，请直接 type='final' ..."
# 预算用完后，最后一次调用会带上 budget_left=0 的 instruct，强制模型输出 final
```

### SSE 流式事件

```python
# backend/kb_qa_agent/api/chat.py
async def _stream_chat(req: ChatRequest):
    yield {"event": "start", "data": {...}}
    intake = classify_intent(req.query, ...)
    yield {"event": "intake", "data": intake}
    plan_bundle = generate_plan(req.query, domain=intake["domain"], ...)
    yield {"event": "plan", "data": {...}}
    # ... step_start / step_result / risk / final
```

### Sandbox 命令白名单

```python
# backend/kb_qa_agent/core/sandbox.py
def _check_command(self, command: str) -> None:
    first_token = command.strip().split(maxsplit=1)[0]
    if not any(first_token.startswith(p) for p in self.allowed_cmd_prefixes):
        raise SandboxError(f"Command {first_token!r} not in whitelist")
```

### Skills frontmatter 解析

```python
# backend/kb_qa_agent/core/skill_loader.py
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
def _parse_frontmatter(text: str) -> dict:
    m = _FRONTMATTER_RE.search(text)
    return yaml.safe_load(m.group(1)) if m else {}
```

## 数据流

详见 [`ARCHITECTURE.md`](ARCHITECTURE.md) 的"数据流"章节，记录一次 `/v1/chat` 请求从前端到 Provider 的完整旅程。
