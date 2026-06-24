# chunking.spec

> Markdown-aware 切分器。`core/chunking.py` 是 RAG 摄取链路上"字符级切分 → 语义级切分"的替换点。
> 与 `core/rag.py` 的 `add_documents()`、`eval/bootstrap_kb.py` 的 `ingest()` 协同工作。

## 1. 用途（Purpose）

把一份 markdown 文档切成若干 `ChunkPiece`，每个 chunk 携带它所属的 heading 路径（"## / ###" 标题层级），便于：
- 检索召回时给 LLM 提供**章节定位上下文**
- 引用渲染时按 `[i] source#heading` 输出
- 摄取幂等时按 chunk id 去重

切分策略：H1/H2/H3 节 → 节内按段落/code fence/表格贪婪打包 → 超长段退化 sliding window。

## 2. 公共 API（Public API）

```python
@dataclass
class ChunkPiece:
    text: str
    heading_path: list[str] = field(default_factory=list)
    char_len: int = 0                       # __post_init__ 自动填 len(text)

def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]: ...
def chunk_markdown(
    raw: str,
    *,
    max_chars: int = 600,
    min_chars: int = 100,
    overlap_chars: int = 80,
    has_frontmatter: bool = True,
) -> list[ChunkPiece]: ...
```

## 3. 输入契约（Input Contract）

| 参数 | 类型 | 约束 | 默认值 | 必需 |
|---|---|---|---|---|
| `raw` | `str` | UTF-8 markdown；允许空字符串 | — | ✅ |
| `max_chars` | `int` | `> 0` | `600` | ❌ |
| `min_chars` | `int` | `> 0 and < max_chars` | `100` | ❌ |
| `overlap_chars` | `int` | `>= 0 and < max_chars` | `80` | ❌ |
| `has_frontmatter` | `bool` | True 时按 `---...---` 剥离 | `True` | ❌ |

frontmatter 是可选的 YAML，解析失败时 fallback 到 `{}`，**不会抛异常**。

## 4. 输出契约（Output Contract）

成功路径：返回 `list[ChunkPiece]`，每条满足：
- `chunk.text` 非空字符串（已 `.strip()`）
- `chunk.heading_path` 是从根到当前节的标题列表，可能为空（无标题的文档）
- `chunk.char_len == len(chunk.text)`（`__post_init__` 保证）

失败路径：参数校验失败（如 `max_chars <= 0`）由调用方负责；本模块不抛业务异常。

## 5. 不变量（Invariants）

- **I1**：每个 chunk 的 `heading_path` 等于该 chunk 文本所在的最小 heading 节之祖先标题列表。
- **I2**：任何单个 chunk 不超过 `max_chars + overlap_chars`（sliding window 的容差）。
- **I3**：code fence 围栏（```` ``` ````）不会跨 chunk 切断；fence 在 chunk 内的出现次数必为偶数。
- **I4**：相邻 `< min_chars` 的 chunk 会被贪婪合并到上一个 chunk（受 `max_chars` 约束），不产生单行 chunk。
- **I5**：frontmatter 文本不进入任何 chunk 的 `text` 字段。
- **I6**：纯文本输入（无任何 `#` 标题）仍产生 ≥ 1 个 chunk，`heading_path = []`。

## 6. 错误模式（Error Modes）

| 触发条件 | 行为 |
|---|---|
| frontmatter YAML 解析失败 | 返回 `({}, raw)`；不抛 |
| 空字符串输入 | 返回 `[]` |
| `max_chars <= 0` | 行为未定义（依赖调用方传合法值） |
| 单段超 `max_chars` | sliding window 兜底，仍保留 heading_path |

## 7. 边界情况（Edge Cases）

- 空文档：返回 `[]`
- 只有 frontmatter 没有正文：返回 `[]`
- 没有标题的纯段落：返回 `[(text, [])]` 单 chunk
- 超长单段（> 10× max_chars）：sliding window 切成多个，每个仍带原 heading_path
- code block 内含 `#` 字符：不被识别为 heading（fence 内跳过 `_HEADING_RE`）
- 嵌套 heading（H2 后接 H3 再回到 H2）：栈式管理，H3 不会逃出 H2 之后存活

## 8. 性能预期（Performance）

- 典型 10KB 文档：< 5 ms
- 100KB 文档：< 50 ms
- 内存：每 chunk 仅持有一份 text + heading_path，无额外副本

## 9. 不在本模块范围（Non-Chunking Goals）

- 不负责去重 / 幂等写入（`core/rag.py` 负责，按 source + sha1 生成 id）
- 不负责 embedding（`core/rag.py` 的 `_ensure_embed_fn` 负责）
- 不负责 frontmatter schema 校验（解析失败静默降级）
- 不切 HTML / reStructuredText（仅 markdown）

## 10. 依赖（Dependencies）

- 内部：无（纯 Python，被 `core/rag.py` 和 `eval/bootstrap_kb.py` 调用）
- 外部：`pyyaml`（frontmatter 解析）
- 环境变量：无
