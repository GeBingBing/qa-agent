"""tool_registry.py — ToolRegistry。

差异点：
  - 增加 side_effect_level 强制分级（read / write / external）
  - 工具签名校验基于 schema dict（可选）
  - async-friendly：支持 sync / async 两种 func
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal


SideEffectLevel = Literal["read", "write", "external"]


@dataclass
class ToolSpec:
    """单个工具的元数据。"""
    id: str
    desc: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    func: Callable[..., Any] = None
    side_effect_level: SideEffectLevel = "read"
    domain: str = ""                # 业务域：hr / finance / it / legal / general
    source: Literal["builtin", "mcp", "skill"] = "builtin"


class ToolRegistry:
    """中央工具注册表。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # ---------- CRUD ----------
    def register(
        self,
        id: str,
        desc: str,
        func: Callable[..., Any],
        *,
        side_effect_level: SideEffectLevel = "read",
        domain: str = "",
        input_schema: dict[str, Any] | None = None,
        source: Literal["builtin", "mcp", "skill"] = "builtin",
    ) -> ToolSpec:
        if id in self._tools:
            raise ValueError(f"Tool id already registered: {id!r}")
        spec = ToolSpec(
            id=id,
            desc=desc,
            input_schema=input_schema or {},
            func=func,
            side_effect_level=side_effect_level,
            domain=domain,
            source=source,
        )
        self._tools[id] = spec
        return spec

    def get(self, id: str) -> ToolSpec:
        return self._tools[id]

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def list_ids(self) -> list[str]:
        return list(self._tools.keys())

    def filter(self, *, domain: str | None = None, side_effect_max: SideEffectLevel | None = None) -> list[ToolSpec]:
        """按业务域 / 副作用级别过滤。"""
        order: dict[SideEffectLevel, int] = {"read": 0, "write": 1, "external": 2}
        out: list[ToolSpec] = []
        for spec in self._tools.values():
            if domain and spec.domain != domain:
                continue
            if side_effect_max and order[spec.side_effect_level] > order[side_effect_max]:
                continue
            out.append(spec)
        return out

    def to_prompt_blocks(self, ids: list[str] | None = None) -> str:
        """把选中的工具渲染成给 LLM 看的描述文本。"""
        specs = [self._tools[i] for i in ids] if ids else self.list()
        lines = []
        for spec in specs:
            schema = spec.input_schema or {}
            lines.append(f"- id: {spec.id}\n  desc: {spec.desc}\n  domain: {spec.domain or 'general'}\n  side_effect: {spec.side_effect_level}\n  input_schema: {schema}")
        return "\n".join(lines)

    # ---------- execution ----------
    async def execute(self, id: str, **kwargs: Any) -> Any:
        spec = self._tools.get(id)
        if spec is None:
            raise KeyError(f"Tool not registered: {id!r}")
        if inspect.iscoroutinefunction(spec.func):
            return await spec.func(**kwargs)
        # sync 函数丢到线程池，避免阻塞事件循环
        return await asyncio.to_thread(spec.func, **kwargs)


# 全局单例（业务模块直接 import 它）
GLOBAL_REGISTRY = ToolRegistry()
