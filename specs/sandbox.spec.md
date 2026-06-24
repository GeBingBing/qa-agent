# sandbox.spec

## 1. 用途

提供受控的 bash 命令执行环境，给 Agent 调用本地 shell 工具的能力，但用三道防线限制风险：命令前缀白名单 + 强制超时 + 工作目录隔离。

> ⚠️ 这是非生产级沙盒——足够阻挡误操作和明显恶意指令，**不**是 OS 级隔离（不防 fork bomb / 资源耗尽 / 路径逃逸符号链接攻击）。生产请用 gVisor / firecracker / Docker --read-only。

## 2. 公共 API

```python
# core/sandbox.py

@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    duration_ms: int = 0

class SandboxError(Exception): ...

class BashSandbox:
    def __init__(
        self,
        workdir: str | None = None,
        allowed_cmd_prefixes: Sequence[str] | None = None,
        timeout: int | None = None,
    ): ...

    async def run(
        self, command: str, *, env_extra: dict[str, str] | None = None
    ) -> SandboxResult
```

## 3. 输入契约

### `__init__`

| 参数 | 类型 | 约束 | 默认值 |
|---|---|---|---|
| `workdir` | `str \| None` | None → 用 SETTINGS.yaml 的 `sandbox.workdir` | `./data/sandbox_workspace` |
| `allowed_cmd_prefixes` | `Sequence[str] \| None` | None → 用 SETTINGS.yaml 配置 | `["python3","ls","cat","head","grep"]` |
| `timeout` | `int \| None` | None → 用 SETTINGS.yaml；解析失败 fallback 到 15 | 15 秒 |

### `run`

| 参数 | 类型 | 约束 |
|---|---|---|
| `command` | `str` | 非空；首 token 必须以 `allowed_cmd_prefixes` 之一开头 |
| `env_extra` | `dict[str, str] \| None` | 注入的额外环境变量；不能覆盖 PATH / HOME（HOME 强制为 workdir）|

## 4. 输出契约

`run` 返回 `SandboxResult`：
- `stdout` / `stderr`：UTF-8 解码（错误字符用 `replace`），可能为空字符串
- `exit_code`：进程退出码；超时时为负数（被 kill，具体值取决于信号：`SIGKILL=-9`，自定义 fallback `-1`）
- `timed_out`：超时时为 `True`，正常完成为 `False`
- `duration_ms`：实际耗时（毫秒）

异常抛出场景：见错误模式。

## 5. 不变量

- **I1**：`workdir` 在 `__init__` 时一定存在（`mkdir parents=True, exist_ok=True`）
- **I2**：超时进程一定被 `proc.kill()` 杀掉，不留僵尸
- **I3**：命令首 token 不在白名单时**必抛** `SandboxError`，绝不执行
- **I4**：进程的 `cwd` 始终是 `workdir`，不论命令内容
- **I5**：进程的 `HOME` 环境变量始终是 `workdir`，避免污染用户主目录
- **I6**：`run` 不抛除 `SandboxError` / 系统级异常（如 OS not enough memory）以外的异常

## 6. 错误模式

| 触发条件 | 异常 | 消息 |
|---|---|---|
| 命令首 token 不在白名单 | `SandboxError` | `"Command 'xxx' not in whitelist. Allowed prefixes: (...)"` |
| `bash` 不在 PATH | `SandboxError` | `"bash is required but not available on PATH"` |
| 命令为空字符串 | `SandboxError` | `"Command 'xxx' not in whitelist..."`（首 token 为空，匹配失败）|

注：超时**不**抛异常，而是返回 `SandboxResult(timed_out=True, exit_code=-1)`。

## 7. 边界情况

- **超长输出**：stdout+stderr 合计超过 `max_output_bytes`（默认 16 MiB）时**截断已读到的内容**并把 `SandboxResult.truncated` 置 True，附 `[... truncated: output exceeded N bytes ...]` 标记；进程仍在写则一并 kill
- **二进制输出**：UTF-8 解码失败时用 `errors="replace"`，不会爆栈
- **管道命令**：白名单只校验首 token，所以 `python3 script.py | head` 会通过；想限管道需自行扩展
- **shell 注入**：`asyncio.create_subprocess_shell` 走 `bash -c '<command>'`，命令本身在 workdir 内执行，但**没有**chroot——能 `cat /etc/passwd`。这是已知非生产级限制
- **并发 run**：每次 `run` 独立 subprocess，互不影响；但都共享同一 `workdir`
- **timeout = 0 或负数**：`asyncio.wait_for(timeout=0)` 立即超时；不推荐

## 8. 性能预期

| 操作 | 典型耗时 |
|---|---|
| `__init__` | < 10ms（mkdir）|
| `run("python3 -c 'print(1)'")` | 100-300ms（启动 Python 解释器）|
| `run("ls")` | 5-30ms |
| 超时路径 | timeout + ~50ms（kill + wait）|

## 9. 不在本模块范围

- 不做 OS 级隔离（chroot / namespace / cgroups）
- 不做资源限制（内存 / CPU / 文件描述符）
- 不做网络隔离（命令仍能访问网络）
- 不做命令解析或参数校验（白名单只看首 token）
- 不做日志持久化（`run` 完成后 SandboxResult 抛给调用方，不落盘）

## 10. 依赖

- 标准库：`asyncio` / `os` / `shutil` / `pathlib`
- 系统要求：`bash` 在 `PATH`
- 配置：`SETTINGS.yaml:sandbox.{workdir,allowed_cmd_prefixes,timeout}`
- 环境变量：`KB_QA_SANDBOX_WORKDIR` / `KB_QA_SANDBOX_TIMEOUT` / `KB_QA_SANDBOX_ALLOWED_CMD_PREFIXES`（通过 SETTINGS.yaml 中转）
