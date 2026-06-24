# chat.spec

> `/v1/chat` SSE 端点契约。P0 / P1 / P2 阶段所有相关改造都以本规范为准。

## 1. 用途（Purpose）

把 `intake → plan → execute → risk → finalize` 五段决策流以 SSE 流式推送到前端，
让前端能实时展示 TracePanel 与打字机式答案，并支持中断与异常兜底。

## 2. 公共 API（Public API）

```python
@router.post("/v1/chat")
async def chat(req: ChatRequest, request: Request) -> EventSourceResponse: ...
```

请求体：

```python
class ChatRequest(BaseModel):
    query: str
    conversation_history: list[dict] = []
    enable_rag: bool = True
    enable_reflection: bool = True
    enable_skills: bool = True
    provider: str | None = None       # 覆盖 active provider；None 时走 .env
    model: str | None = None          # 覆盖 active model
```

## 3. 输入契约（Input Contract）

| 字段 | 类型 | 约束 | 默认值 | 必需 |
|---|---|---|---|---|
| `query` | `str` | `1 <= len(query.strip()) <= 4000` | — | ✅ |
| `conversation_history` | `list[dict]` | 元素含 `role`/`content`；最多 32 条 | `[]` | ❌ |
| `enable_rag` | `bool` | — | `True` | ❌ |
| `enable_reflection` | `bool` | — | `True` | ❌ |
| `enable_skills` | `bool` | — | `True` | ❌ |
| `provider` | `str \| None` | 必须在 `PROVIDER_REGISTRY` 中 | `None` | ❌ |
| `model` | `str \| None` | 字符串校验，下游 SDK 决定合法性 | `None` | ❌ |

P2 引入鉴权后，请求需携带 `Authorization: Bearer <KB_QA_API_TOKEN>`。

## 4. 输出契约（Output Contract）

正常路径：返回 `text/event-stream`，事件序列为：

```
start
intake
plan
[step_start, step_result] × N           # 每个 plan node 一对
sources                                  # 可选：仅当 plan_bundle.rag_hits 非空时
risk
[thinking_delta] × T                     # （可选）模型 <think>...</think> 内增量
[answer_delta] × M                       # 真流式 chunk（P1 起为 LLM 真实增量）
final
```

`thinking_delta` 仅在 `enable_reflection=False` 真流式路径出现；含反思的路径不产生此事件。
`sources` 仅在 `enable_rag=True` 且 `plan_bundle.rag_hits` 非空时出现；用于前端在流式正文之前渲染来源 chip。

异常路径：

```
... 已发生事件 ...
error
final                                    # 必发，content 为兜底说明
```

事件 payload（JSON 字符串）：

| 事件 | 关键字段 |
|---|---|
| `start` | `query: str`, `ts: float` |
| `intake` | `domain`, `intent`, `confidence`, `reasoning`, `needs_tools`, `timestamp` |
| `plan` | `rationale`, `nodes`, `rag_hits_count`, `selected_skills`, `blocked_skills`, `timestamp` |
| `sources` | `id: int`, `source: str`, `heading_path: str`, `score: float`, `snippet: str`（≤ 240 字）|
| `step_start` | `id`, `kind`, `title`, `timestamp` |
| `step_result` | `id`, `kind`, `status`, `content?`, `observation?`, `error?`, `timestamp` |
| `risk` | `risk_level`, `auto_proceed`, `reasons`, `required_approver`, `timestamp` |
| `thinking_delta` | `delta: str`, `timestamp` |
| `answer_delta` | `delta: str`, `timestamp` |
| `final` | `final_answer`, `reflection_rounds`, `evaluations`, `risk_level`, `domain`, `blocked_by_risk?`, `timestamp` |
| `error` | `code: str`, `message: str`, `phase: str`, `timestamp` |

## 5. 不变量（Invariants）

- **I1**：`start` 永远是第一个事件；`final` 永远是最后一个事件。
- **I2**：每个 `step_start` 必有对应的 `step_result`；不得乱序。
- **I3**：`final.final_answer` 一定非空字符串（哪怕是兜底说明）。
- **I4**：`error` 出现后必发 `final`；`final` 不依赖 `error` 是否出现。
- **I5**：`provider` / `model` 显式传入时全链路（intake/plan/exec/reflection）使用同一组配置；未传则走 `KB_QA_ACTIVE_PROVIDER`。
- **I6**：当 `request.is_disconnected()` 为真时，必须停止后续 LLM 调用并退出生成器。
- **I7**：单条事件 `data` 字段是合法 JSON；多行 data 用换行拼接，前端按 SSE 规范合并。
- **I8**：`sources`（若发出）必出现在 `plan` 之后、首个 `answer_delta` / `step_start` 之前；按 `source` 去重（同 source 保留 score 最低那条）。

## 6. 错误模式（Error Modes）

| 触发条件 | 事件序列 | `error.code` | 备注 |
|---|---|---|---|
| Provider 未配置 | `error` → `final` | `provider_unavailable` | `final.final_answer` 含人类可读说明 |
| structured JSON 解析失败 2 次 | `error` → `final` | `structured_parse_failed` | 透传最后一次模型输出截断（≤ 200 字） |
| RAG 检索失败 | （静默继续，trace 记录） | — | `plan.rag_hits_count = 0`，不发 `sources` |
| Skill 选择失败 | （静默继续，trace 记录） | — | `plan.selected_skills = []` |
| 客户端断开 | 立刻停止；不再发事件 | — | server 侧 trace 标记 `disconnected` |
| 鉴权失败（P2 起） | HTTP 401，无 SSE | — | 不进入 `_stream_chat` |
| `query` 校验失败 | HTTP 422 | — | FastAPI 自带 |

## 7. 边界情况（Edge Cases）

- **空 plan**：planner 因模型抖动返回 0 个 node — 跳过 step 阶段，`final.final_answer` 走兜底说明；`risk` 仍会发出。
- **`sources` 去重**：同 `source` 多条命中只展示 score 最低那一条；`snippet` 截断到 240 字；按 score 升序、`id` 从 1 起递增。
- **`sources` 缺失**：当 `enable_rag=False` 或 `plan_bundle.rag_hits` 为空时不发 `sources` 事件；前端降级为不显示来源区。
- **prompt 注入上界**：`_real_stream_answer` 最多把前 4 条 RAG 命中（`MAX_RAG_HITS_INTO_PROMPT`）注入 final 答案的 system/user prompt；超出部分仅出现在 `sources` 事件中。
- **超长 final**：> 8000 字时 `answer_delta` 数量大；客户端按收到顺序累加，不必去重。
- **思考块**：模型输出 `<think>...</think>` 必须在写入 `final.final_answer` 与 `answer_delta` 之前剥离。
- **风险高 + auto_proceed=False**：跳过 reflection，`final.blocked_by_risk = True`，`final.final_answer` 写入审批说明。
- **provider/model 切换**：单次请求生效；不修改 process-level 单例。

## 8. 性能预期（Performance）

| 操作 | 典型耗时 |
|---|---|
| 首字节（`start`） | < 100 ms |
| `intake` | 0.5 - 2 s |
| `plan` | 1 - 4 s |
| `answer_delta` 首块 | ≤ 1.5 s（P1 真流式上线后） |
| 完整响应 | 5 - 30 s（含反思） |

## 9. 不在本模块范围（Non-Goals）

- 不负责会话持久化（前端 localStorage / 后端 Session 单独设计）
- 不负责 token 计费与限流（P2 由 metrics + 单独 middleware 完成）
- 不负责多模态输入（image / file 走专门 endpoint）
- 不负责 streaming 之外的同步响应

## 10. 依赖（Dependencies）

- 内部：`kb_qa_agent.flows.{intake,plan_gen,dep_executor,risk_approval,reflection}`、`kb_qa_agent.providers.*`、`kb_qa_agent.core.rag`、`kb_qa_agent.observability.{tracer,cost}`
- 外部：`fastapi`、`sse-starlette`、`anyio`
- 环境变量：`KB_QA_ACTIVE_PROVIDER`、`KB_QA_ACTIVE_MODEL`、`KB_QA_API_TOKEN`（P2）
