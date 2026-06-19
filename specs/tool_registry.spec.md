# tool_registry.spec

## 1. 用途

提供工具的中央注册表，让 ReAct 循环 / Planner / DAG 执行器都能通过统一接口查询、过滤、执行工具。每个工具带 domain 和副作用级别（read / write / external），便于按权限分级注入。

## 2. 公共 API

```python
# core/tool_registry.py

@dataclass
class ToolSpec:
    id: str
    desc: str
    input_schema: dict
    func: Callable
    side_effect_level: Literal["read","write","external"]
    domain: str
    source: Literal["builtin","mcp","skill"]

class ToolRegistry:
    def register(
        self, id: str, desc: str, func: Callable, *,
        side_effect_level: SideEffectLevel = "read",
        domain: str = "",
        input_schema: dict | None = None,
        source: Literal["builtin","mcp","skill"] = "builtin",
    ) -> ToolSpec
    def get(self, id: str) -> ToolSpec
    def list(self) -> list[ToolSpec]
    def list_ids(self) -> list[str]
    def filter(self, *, domain: str | None = None,
               side_effect_max: SideEffectLevel | None = None) -> list[ToolSpec]
    def to_prompt_blocks(self, ids: list[str] | None = None) -> str
    async def execute(self, id: str, **kwargs) -> Any

GLOBAL_REGISTRY: ToolRegistry  # 进程级单例
```

## 3. 输入契约

### `register`

| 参数 | 类型 | 约束 |
|---|---|---|
| `id` | `str` | 非空；snake_case；进程内唯一 |
| `desc` | `str` | 非空；面向 LLM 描述用途和参数 |
| `func` | `Callable` | sync 或 async 都可；参数必须用 keyword-only |
| `side_effect_level` | `Literal["read","write","external"]` | 默认 `"read"` |
| `domain` | `str` | 4 域之一（hr/finance/it/legal）或空（general） |
| `input_schema` | `dict \| None` | JSON Schema dict 或 None（无参数）|
| `source` | `Literal["builtin","mcp","skill"]` | 默认 `"builtin"` |

### `filter`

| 参数 | 类型 | 约束 |
|---|---|---|
| `domain` | `str \| None` | None → 不按 domain 过滤 |
| `side_effect_max` | `Literal["read","write","external"] \| None` | 上限：`read` 只返回 read；`write` 返回 read+write；`external` 返回所有 |

### `execute`

| 参数 | 类型 | 约束 |
|---|---|---|
| `id` | `str` | 必须已注册 |
| `**kwargs` | dict | 应符合该工具的 `input_schema` |

## 4. 输出契约

- `register` 返回 `ToolSpec`，并把 spec 写入 registry
- `get(id)` 返回 `ToolSpec`，未注册时抛 `KeyError`
- `list()` 返回当前所有已注册工具的 list（顺序按注册先后）
- `filter()` 返回过滤后的 list；可能为空
- `to_prompt_blocks()` 返回多行字符串，每个工具一段 `id/desc/domain/side_effect/input_schema`
- `execute()` 返回工具函数本身的返回值；async 函数 await，sync 函数 `asyncio.to_thread` 包装

## 5. 不变量

- **I1**：`id` 在 registry 内全局唯一，重复注册抛 `ValueError`
- **I2**：`get(id)` 拿到的 `ToolSpec` 与 `register` 时传入的字段一致
- **I3**：`execute` 调用前后 registry 状态不变
- **I4**：`filter(side_effect_max="read")` 不会返回任何 `write` / `external` 工具
- **I5**：sync 工具函数不会阻塞事件循环（`execute` 内用 `asyncio.to_thread`）

## 6. 错误模式

| 触发条件 | 异常 | 消息 |
|---|---|---|
| 重复注册同一 id | `ValueError` | `"Tool id already registered: 'xxx'"` |
| `get` / `execute` 未注册 id | `KeyError` | `"Tool not registered: 'xxx'"` |
| `execute` 时工具函数抛错 | 透传 | — |

## 7. 边界情况

- **空 registry**：`list()` 返回 `[]`，`filter()` 返回 `[]`
- **filter 没匹配**：返回 `[]`，不抛错
- **input_schema=None**：工具可调用，参数不校验（registry 不强制做）
- **重复 bootstrap**：domains/__init__.py:bootstrap() 用 `_BOOTSTRAPPED` flag 保证幂等
- **并发 execute**：每个 ToolSpec 的 func 必须自己保证线程安全（registry 不加锁）

## 8. 性能预期

- `register` / `get` / `list_ids`：O(1) 字典操作
- `filter`：O(n)，n = 已注册工具数
- `to_prompt_blocks`：O(n)，n = 选中工具数；输出长度 ~ 100-500 字符/工具
- `execute`：取决于工具本身

## 9. 不在本模块范围

- 不做 input validation（传给工具前 schema 校验由 ReAct loop / dep_executor 做）
- 不做权限审批（`apply_trust_gate` 在 skill_loader 做）
- 不做 RBAC（角色级访问控制）
- 不持久化（进程退出后 registry 清空）

## 10. 依赖

- 标准库：`asyncio` / `inspect` / `dataclasses`
- 不依赖任何业务模块（被 core/ 其他模块依赖）
