"""sandbox.py — 受控执行环境。

设计：
  - 沙盒工作目录可配置（默认 ./data/sandbox_workspace）
  - 命令白名单（按前缀匹配：python3, ls, cat, head, grep）
  - 超时强制（asyncio.wait_for）
  - 输出按 stdout/stderr 捕获
  - **stdout/stderr 合计大小上限** `max_output_bytes`（默认 16MB），超出则在保留 process 退出码的前提下把已读到的输出截断并标记 `truncated`
  - 不允许访问白名单外的目录

注：这是非生产级沙盒——足够阻挡误操作，**不**是 OS 级隔离。
生产请用 gVisor / firecracker / Docker --read-only 等。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..config import get_config

DEFAULT_MAX_OUTPUT_BYTES = 16 * 1024 * 1024  # 16 MiB


class SandboxError(Exception):
    pass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    truncated: bool = False        # 输出超过 max_output_bytes 后被截断
    duration_ms: int = 0


class BashSandbox:
    """受限 bash sandbox。"""

    def __init__(
        self,
        workdir: str | None = None,
        allowed_cmd_prefixes: Sequence[str] | None = None,
        timeout: int | None = None,
        max_output_bytes: int | None = None,
    ):
        cfg = get_config().get("sandbox", {}) or {}
        self.workdir = Path(workdir or cfg.get("workdir") or "./data/sandbox_workspace").resolve()
        prefixes = allowed_cmd_prefixes if allowed_cmd_prefixes is not None else (
            (cfg.get("allowed_cmd_prefixes") or "python3,ls,cat,head,grep").split(",")
        )
        self.allowed_cmd_prefixes = tuple(p.strip() for p in prefixes if p.strip())
        raw_timeout = cfg.get("timeout") or 15
        try:
            self.timeout = int(timeout or raw_timeout)
        except (ValueError, TypeError):
            self.timeout = 15
        raw_cap = max_output_bytes if max_output_bytes is not None else cfg.get("max_output_bytes")
        try:
            self.max_output_bytes = int(raw_cap) if raw_cap else DEFAULT_MAX_OUTPUT_BYTES
        except (ValueError, TypeError):
            self.max_output_bytes = DEFAULT_MAX_OUTPUT_BYTES
        if self.max_output_bytes <= 0:
            self.max_output_bytes = DEFAULT_MAX_OUTPUT_BYTES
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _check_command(self, command: str) -> None:
        first_token = command.strip().split(maxsplit=1)[0] if command.strip() else ""
        if not any(first_token.startswith(p) for p in self.allowed_cmd_prefixes):
            raise SandboxError(
                f"Command {first_token!r} not in whitelist. "
                f"Allowed prefixes: {self.allowed_cmd_prefixes}"
            )

    async def run(self, command: str, *, env_extra: dict[str, str] | None = None) -> SandboxResult:
        """异步执行一条命令。

        输出大小受 `max_output_bytes` 约束：stdout+stderr 字节数超出后**不再读**（kill process），
        并把已捕获部分 + 截断标记返回，标记 `truncated=True`。
        超时单独由 `timeout` 控制，到点后同样 kill，stderr 写入 `(timeout after Ns)`。
        """
        self._check_command(command)
        if not shutil.which("bash"):
            raise SandboxError("bash is required but not available on PATH")

        env = os.environ.copy()
        env["PS1"] = ""
        env["HOME"] = str(self.workdir)
        if env_extra:
            env.update(env_extra)

        start = asyncio.get_event_loop().time()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.workdir),
            env=env,
        )
        cap = self.max_output_bytes
        truncated = False

        async def read_with_cap(stream: asyncio.StreamReader) -> bytes:
            """读流直到 EOF；累计字节数超 cap 时 kill 并截断。"""
            nonlocal truncated
            buf = bytearray()
            while True:
                chunk = await stream.read(8192)
                if not chunk:
                    return bytes(buf)
                buf.extend(chunk)
                if len(buf) > cap:
                    truncated = True
                    buf = buf[: max(0, cap - 200)]
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                    return bytes(buf)

        timer_fired = False

        async def timeout_watch():
            nonlocal timer_fired
            try:
                await asyncio.sleep(self.timeout)
                timer_fired = True
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            except asyncio.CancelledError:
                pass

        timer = asyncio.create_task(timeout_watch())
        try:
            stdout_b, stderr_b = await asyncio.gather(
                read_with_cap(proc.stdout),
                read_with_cap(proc.stderr),
            )
            await proc.wait()
        finally:
            timer.cancel()

        duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)

        stdout_text = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
        stderr_text = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""

        if truncated:
            tag = f"\n\n[... truncated: output exceeded {cap} bytes ...]"
            if stdout_text:
                stdout_text = stdout_text + tag
            else:
                stderr_text = stderr_text + tag

        if timer_fired:
            stderr_text = (stderr_text + f"\n(timeout after {self.timeout}s)").strip()

        return SandboxResult(
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            timed_out=timer_fired,
            truncated=truncated,
            duration_ms=duration_ms,
        )


__all__ = ["BashSandbox", "SandboxResult", "SandboxError", "DEFAULT_MAX_OUTPUT_BYTES"]
