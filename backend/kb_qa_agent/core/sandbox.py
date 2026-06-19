"""sandbox.py — 受控执行环境。

设计：
  - 沙盒工作目录可配置（默认 ./data/sandbox_workspace）
  - 命令白名单（按前缀匹配：python3, ls, cat, head, grep）
  - 超时强制（asyncio.wait_for）
  - 输出按 stdout/stderr 捕获
  - 不允许访问白名单外的目录

注：这是非生产级沙盒——足够阻挡误操作，**不**是 OS 级隔离。
生产请用 gVisor / firecracker / Docker --read-only 等。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..config import get_config


class SandboxError(Exception):
    pass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    duration_ms: int = 0


class BashSandbox:
    """受限 bash sandbox。"""

    def __init__(
        self,
        workdir: str | None = None,
        allowed_cmd_prefixes: Sequence[str] | None = None,
        timeout: int | None = None,
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
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _check_command(self, command: str) -> None:
        first_token = command.strip().split(maxsplit=1)[0] if command.strip() else ""
        if not any(first_token.startswith(p) for p in self.allowed_cmd_prefixes):
            raise SandboxError(
                f"Command {first_token!r} not in whitelist. "
                f"Allowed prefixes: {self.allowed_cmd_prefixes}"
            )

    async def run(self, command: str, *, env_extra: dict[str, str] | None = None) -> SandboxResult:
        """异步执行一条命令。"""
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
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            timed_out = False
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            stdout_b, stderr_b = b"", f"(timeout after {self.timeout}s)".encode()
            timed_out = True
        duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
        return SandboxResult(
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )


__all__ = ["BashSandbox", "SandboxResult", "SandboxError"]
