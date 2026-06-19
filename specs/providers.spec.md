# providers.spec

## 1. 用途

把 7 家 LLM Provider（minimax / kimi / openai / glm / dashscope / deepseek / opus）统一在 `BaseProvider` 协议下，让业务层不感知协议差异（OpenAI 兼容 vs Anthropic）。支持运行时按 `KB_QA_ACTIVE_PROVIDER` 切换。

## 2. 公共 API

```python
# providers/base.py
class BaseProvider(Protocol):
    name: str
    def available(self) -> bool: ...
    def chat(self, messages, *, model=None, temperature=0.7, max_tokens=None, **kw) -> ChatResponse: ...
    def structured(self, messages, schema, *, model=None, temperature=0.3, max_tokens=None, **kw) -> dict: ...
    def stream(self, messages, *, model=None, **kw) -> AsyncIterator[StreamChunk]: ...
    def count_tokens(self, text, *, model=None) -> int: ...
    def price_per_1k(self, model, direction: Literal["input","output"]) -> float: ...

# providers/registry.py
PROVIDER_REGISTRY: dict[str, BaseProvider]
def get_provider(name: str) -> BaseProvider
def list_available() -> list[str]
def list_all() -> list[str]
def active_provider() -> tuple[str, BaseProvider]
```

## 3. 输入契约

### `chat` / `structured` / `stream`

| 参数 | 类型 | 约束 |
|---|---|---|
| `messages` | `list[ChatMessage] \| list[dict]` | 至少 1 条；最后一条 role 应为 `user` 或 `tool` |
| `schema`（仅 structured） | `dict` | 顶层 `{"type":"object","properties":{...},"required":[...]}` |
| `model` | `str \| None` | None → 用 provider 默认 |
| `temperature` | `float` | `[0.0, 2.0]` |
| `max_tokens` | `int \| None` | None → provider 默认 |

### `get_provider`

| 参数 | 类型 | 约束 |
|---|---|---|
| `name` | `str` | 必须在 `PROVIDER_REGISTRY` 的 7 家中 |

## 4. 输出契约

### `chat`

返回 `ChatResponse(content: str, usage: dict, model: str, raw: Any)`：
- `content` 一定非 None（即使空字符串）
- `usage` 含 `prompt_tokens` / `completion_tokens` / `total_tokens` 三键（值 ≥ 0）
- `model` 是真实使用的 model id

### `structured`

返回 `dict`：
- 顶层字段满足 schema 的 `required`
- 顶层字段类型匹配 schema 的 `properties`
- **不**保证嵌套字段 100% 符合 schema（嵌套校验交给业务层）

### `stream`

异步迭代器，每个 yield `StreamChunk(delta: str, done: bool, usage: dict|None, raw: Any)`：
- 至少有一个 `delta != ""` 的 chunk
- 最后一个 chunk `done = True`，可能携带 `usage`

### `available`

`True` ⟺ `api_key` 和 `base_url`(OpenAI 兼容)/`api_key`(Anthropic) 都已配置。

## 5. 不变量

- **I1**：`PROVIDER_REGISTRY` 在进程生命周期内 keys 固定为 7 家
- **I2**：`available() == False` 时调 `chat / structured / stream` 必须抛 `RuntimeError`，不能静默失败
- **I3**：所有 Provider 共享同一 `ChatMessage` / `ChatResponse` / `StreamChunk` 类型
- **I4**：`structured` 返回的 dict 一定包含 schema 的所有 `required` 字段
- **I5**：`price_per_1k` 返回值 ≥ 0；未定价时返回 0.0
- **I6**：`count_tokens("") == 0`

## 6. 错误模式

| 触发条件 | 异常 | 消息 |
|---|---|---|
| Provider 未配置 key | `RuntimeError` | `"Provider 'xxx' not configured (missing api_key/base_url)."` |
| `get_provider("unknown")` | `KeyError` | `"Unknown provider: 'unknown'. Available: [...]"` |
| Schema 不合法 | `ValueError` | `"Schema must have type=object"` |
| 模型返回非 JSON（structured） | `ValueError` | `"Model output is not valid JSON: <reason>"` |
| 模型返回缺 required 字段 | `ValueError` | `"Missing required field: <key>"` |
| 模型返回字段类型不匹配 | `ValueError` | `"Field 'xxx' expected str, got int"` |
| 网络错 / 超时 | 透传 SDK 异常 | — |

## 7. 边界情况

- **空 messages 列表**：透传给 SDK，由 SDK 决定（通常 SDK 会 400）
- **System message 多于一条**：所有 Provider 都把它们 concat（用 `\n\n` 分隔）
- **Anthropic 拆 system**：Claude 协议要求 system 单独传，`claude.py:_split_system()` 自动拆
- **JSON 围栏**：模型用 ` ```json ... ``` ` 包了 JSON，`structured.py:parse_json_response()` 自动剥
- **Structured 重试**：第一次解析失败，把错误回灌给模型重试一次；仍失败抛
- **Active provider 切换**：进程级单例，改 env 后必须重启

## 8. 性能预期

| 操作 | 典型耗时 |
|---|---|
| `chat`（短输入） | 0.5 - 3s |
| `structured`（含一次重试预算） | 1 - 6s |
| `stream` 首 chunk | 0.3 - 1s |
| `count_tokens` | < 5ms（字符近似） |
| `available()` | < 1ms |

## 9. 不在本模块范围

- 不负责调用 retry / 重试策略（业务层用 `tenacity` 或自己包装）
- 不负责 prompt 模板渲染
- 不负责 token 实际计费（只估算）
- 不负责 streaming chunk 的 SSE 包装（`api/chat.py` 做）

## 10. 依赖

- `openai` SDK ≥ 1.30（OpenAI 兼容协议 6 家）
- `anthropic` SDK ≥ 0.30（Claude / Opus）
- 环境变量：每家 `<NAME>_API_KEY` / `<NAME>_BASE_URL` / `<NAME>_DEFAULT_MODEL` + `KB_QA_ACTIVE_PROVIDER`
