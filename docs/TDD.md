# Test-Driven Development（TDD）

> 本项目用 TDD 驱动核心模块开发：先写失败的测试 → 实现让它通过 → 重构。

## 为什么 TDD 对 LLM 项目特别重要

LLM 应用一旦上规模就有三个让人头疼的问题：

1. **行为漂移**：同样的 prompt，不同 Provider / 不同 model 版本可能输出不同
2. **回归隐蔽**：改了 schema 解析逻辑，结果某个 Provider 的边角 case 默默挂掉
3. **集成爆炸**：RAG + Tools + Skills + Sandbox + Reflection 五件套耦合后，定位 bug 像查海难

TDD 是这三个问题的最直接解药：
- 用测试**冻结**已知行为，防止重构破坏
- 用测试**隔离**模块，让 bug 定位精准
- 用测试**对照** spec，让实现不偏离规范

## 红绿重构

```
┌─────────────┐
│  红 (Red)   │  写一个失败的测试。明确"我想要的行为"。
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  绿 (Green) │  写最少代码让测试过。允许丑陋。
└──────┬──────┘
       │
       ↓
┌─────────────┐
│ 重构(Refactor)│  在测试保护下清理代码。
└─────────────┘
```

每一轮**只解决一件事**。绝不跳过红直接写实现。

## 三种测试层次

### 1. 单元测试（unit）—— 主力

- 一个测试一个函数/方法
- 不依赖网络、不依赖 LLM、不依赖文件系统（除非测试目标就是 fs）
- 跑得快（< 1s 单测，整套 < 30s）
- 覆盖率目标：核心模块 ≥ 80%

存放：`backend/tests/test_<module>.py`

### 2. 集成测试（integration）—— 关键路径

- 跨多个模块协作
- 可以用真实 ChromaDB / SQLite，但**不**用真实 LLM
- 用 `monkeypatch` mock Provider 的 `chat / structured / stream`

存放：`backend/tests/test_<flow>_integration.py`，文件名带 `_integration`

### 3. 真实 LLM 测试（live）—— 偶尔跑

- 调真实 Provider，验证端到端
- 用 `@pytest.mark.live` 标记
- CI 默认跳过：`pytest -m "not live"`

存放：`backend/tests/test_live_<scenario>.py`

## 命名约定

```
backend/tests/
├── conftest.py                     共享 fixture
├── test_providers.py               单元：Provider 适配层
├── test_tool_registry.py           单元：ToolRegistry
├── test_planner.py                 单元：Plan / 拓扑 / 校验
├── test_sandbox.py                 单元：Sandbox 白名单 + 超时
├── test_skill_loader.py            单元：Skills 加载 + 信任门
├── test_router.py                  单元：意图路由（mock LLM）
├── test_chat_integration.py        集成：/v1/chat 端到端（mock Provider）
└── test_live_chat.py               live：真实 Provider 烟雾
```

测试函数命名：`test_<scenario>_<expected>`，例如：
- `test_register_duplicate_id_raises_value_error`
- `test_topological_order_with_cycle_raises_planner_error`
- `test_sandbox_blocks_command_not_in_whitelist`

## 运行

```bash
cd backend

# 全部（不含 live）
uv run pytest -v

# 单个文件
uv run pytest tests/test_planner.py -v

# 单个测试
uv run pytest tests/test_planner.py::test_topological_order_simple -v

# 含 live
uv run pytest -v -m "live or not live"

# 覆盖率报告
uv run pytest --cov=kb_qa_agent --cov-report=term-missing
```

## Mock 策略

### Mock Provider

LLM 调用一律 mock，避免测试依赖网络：

```python
@pytest.fixture
def mock_provider(monkeypatch):
    from kb_qa_agent.providers import PROVIDER_REGISTRY
    fake = FakeProvider()  # 你写的 stub
    monkeypatch.setitem(PROVIDER_REGISTRY, "fake", fake)
    monkeypatch.setenv("KB_QA_ACTIVE_PROVIDER", "fake")
    return fake
```

`FakeProvider` 应当实现 `BaseProvider` 协议，`structured` 返回预设 dict，`chat` 返回预设字符串。

### Mock 文件系统

用 `tmp_path` fixture（pytest 内置），不用真实路径：

```python
def test_load_decision_cards_from_dir(tmp_path: Path):
    skill_dir = tmp_path / "fake-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: fake-skill\n---\nbody")
    cards = load_decision_cards(tmp_path)
    assert len(cards) == 1
```

### Mock 时间 / 随机数

少用，但需要时用 `monkeypatch.setattr(time, "time", lambda: 1234567890)`。

## 反模式（不要写这种测试）

❌ **依赖网络**：调真实 OpenAI API，CI 上跑就挂

❌ **依赖运行顺序**：第一个测试改了全局 state，第二个才过

❌ **断言"调了几次"**：脆弱，重构一改就挂；只断言"行为可观察的输出"

❌ **整个 chat 流程一个测试**：500 行的测试，挂了根本不知道哪步错；拆成多个

❌ **复制 print 调试断言**：用 `assert ... == ...`，不要 `print` 结果让人肉眼看

## 已有测试索引

| 文件 | 测试目标 | 依赖 |
|---|---|---|
| `test_providers.py` | Provider 注册 / 可用性 / structured 解析 / 价格 | mock OpenAI client |
| `test_tool_registry.py` | 注册 / 查询 / 过滤 / execute / 重复注册抛错 | 无 |
| `test_planner.py` | Plan 校验 / 拓扑排序 / 环检测 / max_retries | 无（不调 LLM）|
| `test_sandbox.py` | 白名单 / 超时 / 工作目录 / OK 路径 | bash + python3 在 PATH |
| `test_skill_loader.py` | frontmatter 解析 / select_required / trust gate | tmp_path |
| `test_router.py` | route_query 返回结构 / 域归一化 | mock Provider |
| `test_chat_integration.py` | /v1/chat SSE 事件流完整性 | mock Provider + TestClient |

## 工作流速查

```
新需求来了
  ↓
读 specs/<module>.spec.md    ← 没有就先写
  ↓
写 backend/tests/test_<module>.py 里的失败用例
  ↓
跑 pytest，确认它真的红了（不是 import error）
  ↓
写最少实现让它绿
  ↓
跑全套 pytest，确认没破坏其他测试
  ↓
重构（保持绿）
  ↓
更新 docs/CODE_MAP.md
  ↓
git commit
```
