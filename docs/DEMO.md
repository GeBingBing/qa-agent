# Demo / 5 分钟体验

> 假设你已经按 README「快速开始」启动好后端 + 前端，本文带你 5 分钟把每条核心能力跑一遍。
> 命令都在 macOS / Linux 终端可直接执行；后端默认监听 `127.0.0.1:8000`。

---

## 1. 三个探活端点

```bash
# liveness：进程就绪即返回
curl -s http://127.0.0.1:8000/health | jq
```

```json
{
  "status": "ok",
  "active_provider": "minimax",
  "available_providers": ["dashscope", "minimax"],
  "total_tools": 12,
  "skills_loaded": 10
}
```

```bash
# readiness：探测 active provider 是否真可用
curl -s http://127.0.0.1:8000/health/ready | jq
```

```json
{
  "status": "ready",
  "checks": {
    "active_provider": {
      "ok": true,
      "name": "minimax",
      "available_others": ["dashscope", "minimax"]
    }
  }
}
```

```bash
# Prometheus metrics
curl -s http://127.0.0.1:8000/metrics | head -10
```

```
# HELP kb_qa_health_requests_total Number of /health requests
# TYPE kb_qa_health_requests_total counter
kb_qa_health_requests_total 3.0
# HELP kb_qa_chat_requests_total Number of /v1/chat requests
# TYPE kb_qa_chat_requests_total counter
kb_qa_chat_requests_total{provider="minimax",status="ok"} 1.0
# HELP kb_qa_chat_latency_seconds End-to-end /v1/chat latency
# TYPE kb_qa_chat_latency_seconds histogram
kb_qa_chat_latency_seconds_bucket{le="5"} 1.0
```

---

## 2. SSE 流式问答（带反思）

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"query": "我下个月想休 5 天年假，需要什么流程？"}'
```

事件序列（带反思路径，typewriter）：

```
event: start
data: {"query": "...", "ts": 1.7e9}

event: intake
data: {"domain":"hr","intent":"leave_request","confidence":0.95,...}

event: plan
data: {"rationale":"...","nodes":[{"id":"...","kind":"tool",...}],...}

event: step_start
data: {"id":"query_leave_balance","kind":"tool","title":"查询余额"}
event: step_result
data: {"id":"query_leave_balance","kind":"tool","status":"ok","observation":{...}}

event: step_start
data: {"id":"answer","kind":"llm","title":"回答"}
event: step_result
data: {"id":"answer","kind":"llm","status":"ok","content":"..."}

event: risk
data: {"risk_level":"low","auto_proceed":true,...}

event: answer_delta            # typewriter 切片
data: {"delta":"年假申请流程"}
... (M 条)

event: final
data: {"final_answer":"...","reflection_rounds":1,"evaluations":[...]}
```

## 3. 真 LLM 流式（DeepSeek 风格三段式）

关掉反思 → `provider.stream()` 直推增量，`<think>` 块走独立信道：

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"你是谁？", "enable_reflection": false, "enable_rag": false, "enable_skills": false}'
```

事件序列（真流式路径）：

```
start → intake → plan
[step_start, step_result] × N
risk
event: thinking_delta          # 模型 <think>...</think> 内的增量
data: {"delta":"我先想想"}
... (T 条)
event: answer_delta            # 真实 chunk，粗粒度
data: {"delta":"hello "}
... (M 条)
event: final
data: {"final_answer":"hello world","reflection_rounds":0,...}
```

> 前端会把 `thinking_delta` 渲染为可折叠的「思考中…」面板（DeepSeek 风格），
> 思考结束后自动收起，让位给最终 markdown 正文。

## 4. 单次请求覆盖 provider / model

```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"hi", "provider":"opus", "model":"claude-opus-4-8"}'
```

`request_provider()` ContextVar 让 intake / plan / exec / reflection 全链路使用指定 provider，请求结束后自动恢复。

## 5. Bearer 鉴权（生产模式）

```bash
export KB_QA_API_TOKEN=$(openssl rand -hex 24)
uv run uvicorn kb_qa_agent.main:app --port 8000

# 不带 token → 401
curl -s -X POST http://127.0.0.1:8000/v1/chat -d '{"query":"hi"}' \
  -H 'Content-Type: application/json' -o /dev/null -w "%{http_code}\n"
# 401

# 带 token → 200
curl -s -X POST http://127.0.0.1:8000/v1/chat \
  -H "Authorization: Bearer $KB_QA_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"hi"}' -o /dev/null -w "%{http_code}\n"
# 200
```

`/health` `/metrics` 永远公开，便于 k8s probe / Prometheus scrape。

## 6. 客户端断开自动取消

```bash
# 启一个长请求，2 秒后 ctrl-c：
timeout 2 curl -N -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"写一篇 5000 字的入职指南"}'
```

后端 trace 里能看到请求在 ctrl-c 之后立刻停止下游 LLM 调用，节省 token。

## 7. 跨服务串联：X-Request-Id

```bash
curl -i http://127.0.0.1:8000/health -H 'X-Request-Id: trace-test-001'
```

```
HTTP/1.1 200 OK
x-request-id: trace-test-001          # 透传回来
content-type: application/json
```

不带头时服务端自动生成 UUID。同一 ID 会贯穿日志 / trace JSONL / cost report，便于排查。

## 8. 评估套件

```bash
uv run python -m eval.run_eval --provider deepseek --model deepseek-chat
uv run python -m eval.run_eval --limit 5     # 快速冒烟
```

输出示例：

```
✓ q001 hr  recall=1.00 (5/5)  0.42s
✓ q002 hr  recall=1.00 (3/3)  0.31s
✗ q021 legal high-risk → blocked OK ✅
...
==== Summary ====
pass_rate=0.91  avg_recall=0.86  avg_latency=8.4s  total_usd=0.018
by_provider:
  deepseek  calls=23  prompt=12345  completion=4567  usd=0.018
```

## 9. 前端真实截图（可选）

> 想看视觉效果，可以直接打开 <http://localhost:5173>。本节描述每个面板。

```
┌──────────────────────────────────────┐
│  💬 企业知识库问答                       │
│  7 Provider · RAG · MCP · Skills · SSE │
├──────────────────────────────────────┤
│  Sidebar           │  Chat              │
│  ─────             │  ─────             │
│  状态 ok            │ 用户：年假流程?      │
│  active_provider   │                     │
│  可用 Providers     │ 助手：              │
│  工具 12            │  [hr]              │
│  Skills 10         │  ⚙️ 执行步骤         │
│                    │   #1 🔧 query_leave │
│                    │      ⏳→✅          │
│                    │  ✨ 思考中…         │
│                    │     （折叠）         │
│                    │  ## 直接回答        │
│                    │  • 年假提前 3 天…    │
│                    │  📋 流程             │
│                    │  …                  │
│                    │  [ 复制 ] [ 重新生成 ]│
└──────────────────────────────────────┘
```

可交互能力：
- Stop 按钮：streaming 中红色 ◼ 即时打断
- 思考面板：默认展开，思考完成后自动折叠
- 工具步骤：运行中 spinner，完成后 status badge
- 用户消息：复制 / 编辑回填到输入框
- 助手消息：复制 / 重新生成（基于上一条用户消息重发）
- 清空对话：二次确认弹窗
- 输入框：textarea，Enter 发送 / Shift+Enter 换行
- 刷新页面：对话历史从 localStorage 恢复

---

## 下一步

- 看 [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) 了解系统拓扑与决策
- 看 [`docs/CODE_MAP.md`](CODE_MAP.md) 找到任意能力对应的代码位置
- 看 [`specs/chat.spec.md`](../specs/chat.spec.md) 了解 SSE 协议契约
- 看 [`docs/IMPROVEMENT_ROADMAP.md`](IMPROVEMENT_ROADMAP.md) 看 P0–P3 全部 35 条改造项
