# CLAUDE.md — kb-qa-agent 项目记忆

> 本文件是 Claude Code 在每个新会话开始时自动加载的项目级记忆。
> 内容应当稳定、与项目本身相关，不放临时任务上下文。

## 项目定位

`kb-qa-agent` 是企业知识库问答助手骨架，集成 7 Provider LLM + RAG + MCP + Skills + 沙盒 + 反思 + SSE 流式输出。项目要求工程化质量、清晰架构、完整测试。

## 技术栈与版本约束

- **Python**：3.11+（用了 `match/case`、`X | None` PEP 604 语法、`tomllib`）
- **Agently**：4.x（`Agently.create_agent()` / `create_trigger_flow()` / `set_settings()` / `load_settings()`）
- **TriggerFlow**：作为 Agently 4.x 的子模块（不要 `pip install trigger-flow`）
- **FastAPI**：0.110+
- **ChromaDB**：0.5+（`PersistentClient` API）
- **前端**：React 18 + Vite 5 + TS 5 + Tailwind 3 + shadcn 风格（手写组件，不引入完整 shadcn CLI）
- **包管理**：后端 `uv` 优先（兼容 `pip install -e ".[dev]"`），前端 `pnpm`

## 工作流约定（重要）

### Spec-Driven Development（SDD）
- 新增/修改业务能力前，先看 `specs/<module>.spec.md` 是否已有规范
- 没有就先写 spec：明确"输入 / 输出 / 不变量 / 错误模式 / 边界情况"
- spec 通过后，根据 spec 写测试，测试通过后写实现
- spec 文件里的"输入/输出"段，必须能直接对照成 pytest 用例

### Test-Driven Development（TDD）
- **新增能力**：红 → 绿 → 重构
  - 红：先写一个失败的测试（描述目标行为）
  - 绿：写**最少**代码让测试过
  - 重构：在测试保护下清理代码
- **修改 bug**：先写复现 bug 的失败测试，再修
- **测试位置**：`backend/tests/test_<module>.py`
- **运行**：`cd backend && uv run pytest -v`，单文件 `uv run pytest tests/test_planner.py -v`
- **覆盖率目标**：核心模块（providers/ core/ flows/）≥ 80% 行覆盖

### 提交约定
- 每个 commit 一件事；commit message 用动词开头（"Add ... / Fix ... / Refactor ..."）
- commit message 只描述工程变更，不加入与项目无关的外部语境
- 不主动 `git commit` 或 `git push`，由用户决定

## 代码风格

- **文件头 docstring**：一句话讲这个模块做什么 + 关键 API，不加入与模块职责无关的背景说明
- **函数 docstring**：核心函数必须写；用 Google 风格（Args / Returns / Raises）
- **类型注解**：所有 public API 必须有；优先 `X | None` 而非 `Optional[X]`
- **错误处理**：先验证输入，错误用专门异常类（如 `PlannerError` / `SandboxError`），不裸 `Exception`
- **日志**：`logging.getLogger("kb_qa_agent.<submodule>")`，不用 `print`
- **配置**：所有可调参数走 `SETTINGS.yaml` 或 `.env`，不硬编码

## 常见陷阱（之前踩过的坑）

1. **JSON 不支持下划线数字字面量**：`5_000_000` 在 Python 里合法，在 JSON 里会报错。`data/mock_db/*.json` 必须用 `5000000`
2. **bootstrap 重复注册**：`domains/__init__.py:bootstrap()` 必须幂等，靠 `_BOOTSTRAPPED` flag。修改时不能破坏这个
3. **Skills 路径**：`SETTINGS.yaml` 里的 `base_dir` 必须是绝对路径，否则相对路径会被 CWD 影响。`skill_loader.py` 已加保护：相对路径自动 fallback 到包内默认位置
4. **mock MCP server 临时目录**：sandbox 跑后台 server 时若 `/tmp/claude-501` 满了会 ENOSPC；改用进程内调用 `handle_request()` 测试
5. **Sandbox timeout 空字符串**：`SETTINGS.yaml` 的 `${ENV.KB_QA_SANDBOX_TIMEOUT}` 在 env 未设置时变 `""`，`int("")` 会爆。`BashSandbox.__init__` 已加 try/except fallback 到 15
6. **Agently 4.x API**：`get_async_generator(type=..., specific=...)` 是当前流式调用方式；`response.get_response()` 仍可用但流式优先用 generator
7. **Provider 切换**：改 `KB_QA_ACTIVE_PROVIDER` 后**必须重启** uvicorn，因为 Agently settings 是进程级单例

## 目录速查（找代码）

| 想找... | 看这里 |
|---|---|
| 怎么加新 Provider | `backend/kb_qa_agent/providers/` + `registry.py:_DEFAULT_PRICES` |
| 怎么加新 domain 工具 | `backend/kb_qa_agent/domains/<domain>/__init__.py` + `register()` |
| 怎么加新 Skill | `backend/kb_qa_agent/skills/<skill-name>/SKILL.md`（frontmatter + workflow） |
| SSE 事件流定义 | `backend/kb_qa_agent/api/chat.py:_stream_chat()` |
| 前端 SSE 解析 | `frontend/src/lib/api.ts:streamChat()` |
| 配置项 | `backend/kb_qa_agent/SETTINGS.yaml` + `.env.example` |
| 评估题 | `backend/eval/golden_qa.jsonl` |
| 拓扑排序实现 | `backend/kb_qa_agent/core/planner.py:topological_order` |

## 不要做的事

- 不要在源代码里加入与模块职责无关的背景引用
- 不要在 README / docs 里加入与产品定位无关的外部语境
- 不要把 `.env` 提交到 git（已在 `.gitignore`）
- 不要在 `data/mock_db/*.json` 里用下划线数字
- 不要在 `bootstrap()` 里直接 `_BOOTSTRAPPED = True` 之前抛异常（会导致后续重试失败）
- 不要在测试里依赖真实 LLM 调用——用 mock 或单独标记 `@pytest.mark.live`
- 不要主动 `git commit` / `git push`，等用户明确要求

## 增量改动 checklist

每次有意义的改动应当：
1. **spec** —— 是否需要更新 `specs/<module>.spec.md`？
2. **test** —— 写/改了测试吗？`pytest` 跑过吗？
3. **doc** —— 是否需要更新 `docs/CODE_MAP.md` 的索引或 `docs/ARCHITECTURE.md` 的决策？
4. **CHANGELOG** —— 暂未启用 CHANGELOG.md，重大变更先在 commit 里讲清楚

## 评估与验证

- 单元测试：`cd backend && uv run pytest -v`
- 端到端冒烟：本仓库根目录有现成脚本 `uv run python -m eval.bootstrap_kb` + `uv run python -m eval.run_eval --limit 5`
- 健康检查：启动后 `curl http://localhost:8000/health`，应返回 7 Provider 和 12 工具
