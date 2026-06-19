# observability.spec

> trace + cost + metrics + structured log 的统一契约。P2 阶段所有相关改造以本规范为准。

## 1. 用途（Purpose）

把请求级 trace、token 成本、Prometheus 指标、结构化日志四类信号统一管理，
保证：

- 任意一次 `/v1/chat` 请求可通过 `request_id` 在 trace / cost / log 中相互关联
- 敏感数据（API key、原始 prompt）不会写入磁盘
- 默认 JSONL + 可选 OTLP 双通道

## 2. 公共 API（Public API）

```python
# observability/tracer.py
def span(name: str, *, parent: str | None = None,
         attrs: dict[str, Any] | None = None) -> SpanContext: ...

# observability/cost.py
def record(*, provider: str, model: str, prompt_tokens: int,
           completion_tokens: int, request_id: str | None = None) -> None: ...
def get_report() -> CostReport: ...
def save_report_to_disk() -> None: ...

# observability/logging.py
def install_logging(level: str = "INFO", json_format: bool = True) -> None: ...
def request_id_var() -> contextvars.ContextVar[str]: ...

# observability/otel.py
def install_otel_if_enabled() -> None: ...
```

## 3. 输入契约（Input Contract）

### `tracer.span`

| 参数 | 类型 | 约束 |
|---|---|---|
| `name` | `str` | `^[a-z_][a-z0-9_]*$`，长度 ≤ 64 |
| `parent` | `str \| None` | UUID4 字符串 |
| `attrs` | `dict` | 仅可序列化为 JSON；写入前过 `redact()` |

### `cost.record`

| 参数 | 类型 | 约束 |
|---|---|---|
| `provider` | `str` | 必须是 `PROVIDER_REGISTRY` 7 家之一 |
| `model` | `str` | — |
| `prompt_tokens` / `completion_tokens` | `int` | `>= 0` |
| `request_id` | `str \| None` | UUID4；缺省由 ContextVar 自动注入 |

## 4. 输出契约（Output Contract）

### Trace JSONL（默认）

落到 `${KB_QA_TRACE_DIR}/YYYY-MM-DD.jsonl`，每行一个 span：

```json
{
  "span_id": "uuid4",
  "parent_id": "uuid4 | null",
  "request_id": "uuid4",
  "name": "chat_request",
  "start_ts": 1750000000.0,
  "end_ts": 1750000005.5,
  "duration_ms": 5500,
  "attrs": {"query": "<redacted 50 chars>", ...},
  "error": "ProviderError: ..."
}
```

### Cost JSON

落到 `${KB_QA_COST_REPORT_PATH}`，按 1 分钟节流写盘；内存只保留最近 200 条：

```json
{
  "total_usd": 0.012,
  "by_provider": {"minimax": {"prompt": 0.001, "completion": 0.011}},
  "entries": [
    {"ts": 1750000000.0, "provider": "minimax", "model": "minimax-m2.7",
     "prompt_tokens": 234, "completion_tokens": 567, "usd": 0.0083,
     "request_id": "uuid4"}
  ]
}
```

### Metrics（P2 起）

GET `/metrics` 返回 Prometheus 文本格式：

```
# HELP kb_qa_chat_requests_total chat 请求计数
# TYPE kb_qa_chat_requests_total counter
kb_qa_chat_requests_total{status="ok",provider="minimax"} 42

# HELP kb_qa_chat_latency_seconds chat 端到端时延
# TYPE kb_qa_chat_latency_seconds histogram
kb_qa_chat_latency_seconds_bucket{le="1"} 0
kb_qa_chat_latency_seconds_bucket{le="5"} 30
...

# HELP kb_qa_llm_tokens_total LLM token 消耗
# TYPE kb_qa_llm_tokens_total counter
kb_qa_llm_tokens_total{provider="minimax",direction="prompt"} 12345
```

### 结构化日志

JSON 行格式，所有日志必含：

```json
{"ts": "2026-06-17T22:35:01.234Z", "level": "INFO",
 "logger": "kb_qa_agent.api.chat",
 "request_id": "uuid4", "msg": "...", "extra": {...}}
```

## 5. 不变量（Invariants）

- **I1**：进入 `_stream_chat` 时，`request_id` 必须已在 ContextVar 中可读。
- **I2**：tracer / cost / log 写入前必须经过 `redact(text)`：剥离 `<think>...</think>`、屏蔽 `sk-[A-Za-z0-9_-]{16,}`、截断 query 至 50 字符。
- **I3**：`/metrics` 响应不需要鉴权（仅 internal scrape；用 nginx/k8s NetworkPolicy 控制可达性）。
- **I4**：`get_report()` 返回的快照不可变；并发 `record()` 调用必须用 `_lock` 串行化。
- **I5**：JSONL trace 文件按日期切割；retention 默认 14 天，由 systemd-tmpfiles 或 logrotate 处理（不在代码内做删除）。
- **I6**：`install_otel_if_enabled()` 当且仅当 `OTEL_EXPORTER_OTLP_ENDPOINT` 非空时启用。

## 6. 错误模式（Error Modes）

| 触发条件 | 行为 |
|---|---|
| Trace 文件 IO 错误 | logger.error，不抛；当次 span 丢失 |
| Cost 报告写盘失败 | logger.warning，保留内存；下次再试 |
| OTel exporter 失败 | logger.warning，降级回 JSONL |
| Prometheus 注册器冲突 | 启动期 Fatal（防止重复注册导致计数错位） |
| 日志中出现疑似 secret | 静默 redact，不记录原文 |

## 7. 边界情况（Edge Cases）

- **进程重启**：内存 cost 丢失；磁盘 JSON 仍是最后一次成功写入的快照。
- **请求并发**：`request_id` 由 ContextVar 自动隔离；中间件入口生成。
- **流式响应中断**：tracer 在 `finally` 块中关闭根 span，记录 `error`；cost 已 record 的不会回滚。
- **超大 attrs**：`attrs` 序列化后 > 4 KB 时截断到 4 KB 末尾追加 `…(truncated)`。

## 8. 性能预期（Performance）

| 操作 | 典型耗时 |
|---|---|
| `tracer.span` 进出 | < 1 ms |
| `cost.record` | < 1 ms（含 lock） |
| Prometheus scrape | < 50 ms（默认指标量） |
| OTel batch flush | 每 5 秒一次（exporter 默认） |

## 9. 不在本模块范围（Non-Goals）

- 不做日志聚合 / 中央存储（由外部 ELK / Loki / OpenSearch 完成）
- 不做 trace 可视化（由 Jaeger / Tempo / Grafana 完成）
- 不做异常告警（由 Alertmanager / PagerDuty 完成）
- 不做 PII 自动发现（仅做已知模式 redact）

## 10. 依赖（Dependencies）

- 内部：`kb_qa_agent.providers.*`（provider 名一致性）
- 外部：`prometheus_client`（P2 起）、`opentelemetry-api`、可选 `opentelemetry-sdk`、`opentelemetry-exporter-otlp-proto-http`
- 环境变量：
  - `KB_QA_TRACE_DIR`（默认 `./.traces`）
  - `KB_QA_TRACE_LEVEL`（默认 `INFO`）
  - `KB_QA_COST_REPORT_PATH`（默认 `./.cost/report.json`）
  - `OTEL_EXPORTER_OTLP_ENDPOINT`（可选）
  - `OTEL_SERVICE_NAME`（默认 `kb-qa-agent`）
