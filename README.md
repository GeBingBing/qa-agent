# kb-qa-agent

> 企业知识库问答助手 —— 多 Provider LLM + RAG + MCP + Skills + 沙盒 + 反思 + SSE 流式 的端到端 Agent 骨架。

![architecture](docs/ARCHITECTURE.md)

## 这是什么

`kb-qa-agent` 是一个**生产级参考实现**，把企业知识库问答场景下的核心能力串成一条可运行的流水线：

```
用户问题
  → 意图路由（4 域分类）
  → RAG 检索政策文档 + Skills 选择
  → 模型生成执行 DAG（含 tool/llm/human 三类节点）
  → 拓扑顺序执行
  → 风险评估 + 人工审批路由
  → 反思迭代 ≤2 轮
  → SSE 流式推送最终回答
```

**支持 7 家 LLM Provider**（OpenAI 兼容 6 家 + Anthropic SDK 1 家），切换无需改业务代码。

**支持 4 个业务域**：人事 / 财务 / IT / 法务。每个域暴露内部数据查询工具，并通过 MCP 协议对外提供。

## 核心特性

| 类别 | 能力 |
|---|---|
| **多 Provider** | DeepSeek / OpenAI / Claude Opus / Moonshot Kimi / 智谱 GLM / 通义 Qwen / MiniMax，7 家适配层 |
| **RAG** | ChromaDB + 本地 sentence-transformers 嵌入（bge-small-zh） |
| **Skills** | SKILL.md 声明式撰写 + 关键词预筛 + 模型精筛 + 信任门 |
| **MCP** | 外部高德 MCP + 自建本地 mock MCP server（std lib JSON-RPC） |
| **沙盒** | 命令白名单 + 超时 + 工作目录隔离 |
| **多步决策** | 路由 → DAG 规划 → 拓扑执行 → 风险评估 → 反思 |
| **流式输出** | FastAPI SSE 事件流，前端实时渲染 TracePanel |
| **可观测性** | span 跟踪（JSONL）+ token 成本聚合（按 provider 拆账）|
| **评估** | golden_qa 黄金集 + recall + forbidden 短语检测 |
| **前端** | React + Vite + TS + Tailwind + shadcn 风格 + Zustand + TanStack Query |

## 技术栈

**后端**
- Python 3.11+
- [Agently 4.x](https://github.com/AgentEra/Agently) —— Agent / TriggerFlow / Skills runtime
- [TriggerFlow](https://github.com/AgentEra/Agently) —— 多步流程编排
- FastAPI + sse-starlette —— HTTP + SSE
- ChromaDB —— 向量数据库
- httpx / openai / anthropic —— 多 Provider SDK

**前端**
- React 18 + Vite 5 + TypeScript 5
- Tailwind CSS 3（shadcn/ui 变量主题）
- Zustand 4 + TanStack Query 5
- lucide-react

**基础设施**
- ChromaDB（docker-compose）
- 自建 MCP server（docker-compose）
- Docker Compose 一键启动

## 快速开始

```bash
# 1. 准备环境
cp .env.example .env
# 编辑 .env 填入至少一个 Provider 的 API key

# 2. 启动基础设施
docker compose up -d chromadb mock-internal-mcp

# 3. 安装后端依赖
cd backend
uv sync                                # 或 pip install -e ".[dev,eval]"
uv run python -m eval.bootstrap_kb     # 可选：导入政策文档到 ChromaDB

# 4. 启动后端
uv run uvicorn kb_qa_agent.main:app --reload --port 8000

# 5. 启动前端
cd ../frontend
pnpm install
pnpm dev                                # 访问 http://localhost:5173
```

## 验证

### 健康检查

```bash
curl http://localhost:8000/health
# {
#   "status": "ok",
#   "active_provider": "deepseek",
#   "available_providers": ["deepseek", "openai", "opus", ...],
#   "total_tools": 12,
#   "skills_loaded": 4
# }
```

### 端到端问答（curl + SSE）

```bash
curl -N -X POST http://localhost:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"query": "AWS 这份合同是否符合 GDPR？", "enable_reflection": false}'
```

事件流：`start → intake → plan → step_start → step_result → risk → final`

### 评估套件

```bash
cd backend
uv run python -m eval.run_eval --provider deepseek --model deepseek-chat
uv run python -m eval.run_eval --limit 5    # 快速冒烟（5 题）
```

输出含：通过率 / 平均关键词 recall / 平均响应时间 / 总 token 成本 / 按 provider 拆分。

### 切换 Provider

```bash
KB_QA_ACTIVE_PROVIDER=opus \
  uv run uvicorn kb_qa_agent.main:app --reload
```

或单次请求覆盖（`POST /v1/chat` body 的 `provider` / `model` 字段）。

## 项目结构

```
kb-qa-agent/
├── backend/
│   ├── kb_qa_agent/
│   │   ├── providers/      7 Provider 适配层
│   │   ├── core/           10 个核心引擎模块
│   │   ├── domains/        4 域 12 工具
│   │   ├── skills/         4 SKILL.md
│   │   ├── mcp_clients/    高德 + 本地 MCP 客户端
│   │   ├── flows/          5 sub-flow 端到端流水线
│   │   ├── api/            FastAPI 路由
│   │   └── observability/  tracer + cost + eval
│   ├── mock_mcp_servers/   自建 FastMCP server (8765)
│   └── eval/               golden_qa + run_eval + bootstrap_kb
├── frontend/               React + Vite + Tailwind
├── data/
│   ├── knowledge_base/     政策文档
│   └── mock_db/            4 域 mock JSON
└── docs/                   ARCHITECTURE / PROVIDER_SETUP / CODE_MAP
```

## 文档

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) —— 系统拓扑、数据流、关键设计决策
- [`docs/PROVIDER_SETUP.md`](docs/PROVIDER_SETUP.md) —— 7 Provider 注册、配置、切换、定价、故障排查
- [`docs/CODE_MAP.md`](docs/CODE_MAP.md) —— 内部模块索引 + 关键代码片段导览
- [`docs/SDD.md`](docs/SDD.md) —— Spec-Driven Development 方法论
- [`docs/TDD.md`](docs/TDD.md) —— Test-Driven Development 方法论
- [`specs/`](specs/) —— 各模块规范（providers / tool_registry / planner / sandbox）
- [`CLAUDE.md`](CLAUDE.md) —— Claude Code 项目记忆（约定 / 陷阱 / 速查）

## 工程实践

本项目采用 **SDD + TDD** 双驱动：

```
specs/<module>.spec.md          ← 单一事实源
       │
       ├── 决定 → backend/tests/test_<module>.py（97 个测试，全部通过）
       │
       └── 决定 → backend/kb_qa_agent/<module>.py（实现满足规范）
```

跑测试：
```bash
cd backend
uv run pytest -v                                    # 97 tests, ~8s
uv run pytest --cov=kb_qa_agent --cov-report=term   # 含覆盖率
```

详细工作流见 [`docs/SDD.md`](docs/SDD.md) 与 [`docs/TDD.md`](docs/TDD.md)。

## License

MIT
