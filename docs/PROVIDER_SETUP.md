# Provider 配置指南（Provider Setup）

> kb-qa-agent 通过 `providers/registry.py` 中的 `PROVIDER_REGISTRY` 把 7 家 LLM Provider
> 统一在 `BaseProvider` 协议下。切换 Provider 不需要改任何业务代码。

## 总览

| Provider | 协议 | 默认模型 | 备注 |
|---|---|---|---|
| `deepseek`  | OpenAI 兼容 | `deepseek-chat`        | 默认；性价比高 |
| `openai`    | OpenAI 兼容 | `gpt-4o-mini`          | GPT-4o / o-series 都能用 |
| `opus`      | Anthropic SDK | `claude-opus-4-8`    | 唯一非 OpenAI 协议；用 `anthropic` SDK |
| `kimi`      | OpenAI 兼容 | `moonshot-v1-128k`     | 长上下文场景（128k） |
| `glm`       | OpenAI 兼容 | `glm-4-flash`          | 智谱 BigModel |
| `dashscope` | OpenAI 兼容 | `qwen-plus`            | 阿里通义千问 |
| `minimax`   | OpenAI 兼容 | `abab6.5s-chat`        | 第三方 OpenAI 兼容 |

## 三步走

### 1. 注册账号 + 申请 API Key

每个 Provider 控制台不同，按下面链接注册（部分需要实名 / 充值）：

- **DeepSeek**：<https://platform.deepseek.com>（推荐起点，国内可直连）
- **OpenAI**：<https://platform.openai.com/api-keys>（需科学上网）
- **Anthropic（Claude/Opus）**：<https://console.anthropic.com/settings/keys>
- **Moonshot Kimi**：<https://platform.moonshot.cn/console/api-keys>
- **智谱 GLM**：<https://bigmodel.cn/usercenter/apikeys>
- **阿里 DashScope**：<https://dashscope.console.aliyun.com/apiKey>
- **MiniMax**：联系供应商获取

### 2. 填 `.env`

```bash
cp .env.example .env
# 编辑 .env，填入至少一个 Provider 的 API key

# 例如只用 DeepSeek：
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_DEFAULT_MODEL=deepseek-chat

# Active provider (默认就是 deepseek)
KB_QA_ACTIVE_PROVIDER=deepseek
KB_QA_ACTIVE_MODEL=deepseek-chat
```

### 3. 启动 + 验证

```bash
docker compose up -d chromadb mock-internal-mcp
uv run uvicorn kb_qa_agent.main:app --reload --port 8000
# 访问 http://localhost:8000/health
```

`/health` 端点会列出 `available_providers`（填了 key 的 provider）和 `active_provider`（当前用哪个）。

## 切换 Provider

两种方式：

**方式 A：改 `.env` + 重启**

```bash
KB_QA_ACTIVE_PROVIDER=opus uvicorn kb_qa_agent.main:app --reload
```

**方式 B：API 请求级覆盖（待实现）**

`POST /v1/chat` 支持 `provider` / `model` 字段，单次请求覆盖：

```json
{
  "query": "...",
  "provider": "opus",
  "model": "claude-opus-4-8"
}
```

## 验证 7 Provider 全链路兼容

```bash
for p in deepseek openai opus kimi glm dashscope minimax; do
  echo "==== Testing provider: $p ===="
  KB_QA_ACTIVE_PROVIDER=$p python -m pytest tests/test_providers.py::test_smoke -v
done
```

没填 key 的 provider 会自动跳过（pytest 用 `@pytest.mark.skipif`），不会让测试失败。

## 成本感知

每个 Provider 在 `providers/registry.py` 的 `_DEFAULT_PRICES` 表里有默认定价（USD / 1k tokens）：

```python
_DEFAULT_PRICES = {
    "deepseek":   {"input": 0.00014, "output": 0.00028},   # 极便宜
    "openai":     {"input": 0.00015, "output": 0.00060},   # gpt-4o-mini
    "opus":       {"input": 0.015,   "output": 0.075},     # 贵但能力强
    "kimi":       {"input": 0.001,   "output": 0.002},
    "glm":        {"input": 0.0001,  "output": 0.0001},
    "dashscope":  {"input": 0.0008,  "output": 0.002},
    "minimax":    {"input": 0.001,   "output": 0.001},
}
```

每次 LLM 调用，`observability/cost.py` 会按 token 数 × 单价累计成本。`/health` 端点不返回成本，但 `eval/run_eval.py` 跑完会打印 `Total cost` + 按 provider 聚合。

## 故障排查

| 现象 | 排查 |
|---|---|
| `available() = False` | 检查 `.env` 对应 Provider 的 `*_API_KEY` 是否填、是否 trim 了空格 |
| `RuntimeError: Provider 'xxx' not configured.` | 同上；运行时选了 `available()=False` 的 provider |
| Agently 工具调用失败 | `providers/agently_adapter.py` 只在 active provider 上注入 settings；切到不同 provider 需重启 |
| Opus 调不通 | 确认 `anthropic` SDK 安装了 (`pip install anthropic`)，并确认 `ANTHROPIC_BASE_URL` |
| Mock MCP server 起不来 | 看 `data/mock_db/*.json` 是否含下划线数字（JSON 不支持，用 `5000000` 而非 `5_000_000`）|
