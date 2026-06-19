# planner.spec

## 1. 用途

把用户问题 + 上下文 → 一个有向无环图（DAG）的执行计划。每个节点是 `tool` / `llm` / `human` 之一。模型生成后做 Kahn 拓扑排序校验，发现环或孤儿依赖时回灌错误让模型重试。

## 2. 公共 API

```python
# core/planner.py

@dataclass
class PlanNode:
    id: str
    kind: Literal["llm","tool","human"]
    title: str
    description: str = ""
    binding: str = ""
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 1

@dataclass
class Plan:
    rationale: str
    nodes: list[PlanNode]

class PlannerError(Exception): ...

def plan_dag(
    user_query: str, *,
    domain: str,
    available_tools: list[str] | None = None,
    selected_skills: list[str] | None = None,
    extra_context: dict | None = None,
) -> Plan

def plan_with_retry(
    user_query: str, *,
    domain: str,
    available_tools: list[str] | None = None,
    selected_skills: list[str] | None = None,
    extra_context: dict | None = None,
    max_retries: int = 3,
) -> Plan

def validate_plan(plan: Plan) -> None  # raise PlannerError on invalid
def topological_order(plan: Plan) -> list[PlanNode]
```

## 3. 输入契约

### `plan_dag` / `plan_with_retry`

| 参数 | 类型 | 约束 |
|---|---|---|
| `user_query` | `str` | 非空 |
| `domain` | `str` | `hr / finance / it / legal / general` 之一 |
| `available_tools` | `list[str] \| None` | None → 不注入工具 |
| `selected_skills` | `list[str] \| None` | None → 不注入 Skill |
| `extra_context` | `dict \| None` | 任意 JSON-序列化对象（如 RAG hits）|
| `max_retries` | `int` | `≥ 1`；默认 3 |

### `validate_plan`

| 参数 | 类型 | 约束 |
|---|---|---|
| `plan` | `Plan` | 非空 nodes 列表 |

## 4. 输出契约

### `plan_dag` / `plan_with_retry`

返回 `Plan`：
- `rationale` 非空字符串
- `nodes` 长度 ≥ 1
- 每个 `PlanNode.id` 在 plan 内唯一
- 每个 `PlanNode.kind` ∈ {`llm`, `tool`, `human`}
- `depends_on` 中每个 id 都存在于本 plan 的其它 node id 中
- 整个 nodes 形成 DAG（无环）

### `validate_plan`

通过返回 `None`；不通过抛 `PlannerError`。

### `topological_order`

返回 `list[PlanNode]`，按拓扑顺序排列：
- 长度等于 `len(plan.nodes)`
- 任意节点 X 在列表中的位置 < 它的所有后继 Y 的位置

## 5. 不变量

- **I1**：`validate_plan` 通过的 plan，`topological_order` 一定不抛错
- **I2**：`plan_with_retry` 返回的 plan 必定通过 `validate_plan`
- **I3**：`plan_dag` 不重试；可能返回不通过 `validate_plan` 的 plan
- **I4**：`PlanNode.id` 不依赖自己（`X.depends_on` 不含 `X`）
- **I5**：拓扑排序结果中，每个节点的所有依赖节点排在它之前

## 6. 错误模式

| 触发条件 | 异常 | 消息 |
|---|---|---|
| nodes 中 id 重复 | `PlannerError` | `"Plan contains duplicate node ids"` |
| `depends_on` 引用不存在的 id | `PlannerError` | `"Node 'X' depends on unknown node 'Y'"` |
| 节点依赖自己 | `PlannerError` | `"Node 'X' depends on itself"` |
| 存在依赖环 | `PlannerError` | `"Plan contains a dependency cycle"` |
| `kind` 不是 llm/tool/human | `PlannerError` | `"Invalid node kind: 'xxx'"` |
| `plan_with_retry` 重试 max_retries 次仍失败 | `PlannerError` | `"Failed to produce a valid plan after N attempts: ..."` |
| 模型返回非 JSON | 由 `providers.structured` 抛 `ValueError`（被 `plan_with_retry` 捕获重试） | — |

## 7. 边界情况

- **单节点 plan**：合法。`topological_order` 返回 `[node]`
- **平行节点**：多个节点 `depends_on=[]`，`topological_order` 全部排在前面（顺序按 id 字母序）
- **空 available_tools**：传给 LLM 的 prompt 仍合法，模型应当只用 llm/human 节点
- **超大 plan**：模型会被指示节点数 ≤ 8；超过时不强制截断（验证阶段也不拦截，但下游 `dep_executor` 性能可能下降）
- **重试时 prompt 注入**：把上一轮错误信息以 user 消息形式回灌，让模型自我修正

## 8. 性能预期

| 操作 | 典型耗时 |
|---|---|
| `validate_plan` | < 5ms（Kahn 算法 O(V+E)）|
| `topological_order` | < 5ms |
| `plan_dag`（一次成功） | 1-3s（取决于 Provider）|
| `plan_with_retry`（含重试 1 次） | 2-6s |

## 9. 不在本模块范围

- 不执行 plan（`flows/dep_executor.execute_plan` 做）
- 不做参数解析（dep_executor 的 `_resolve_tool_args` 做）
- 不做 RAG 检索（`flows/plan_gen.generate_plan` 做）
- 不做 Skill 选择（`core/skill_loader` 做）

## 10. 依赖

- `core/model_request.py`：`TaskExecutor`
- `providers/`：`ChatMessage` + `BaseProvider.structured`
- 标准库：`dataclasses` / `typing`
