"""flows/dep_executor.py — DAG 执行器。

按拓扑顺序遍历 PlanNode，逐个执行：
  - kind=tool  → await GLOBAL_REGISTRY.execute(node.binding, **args)
  - kind=llm   → 调 TaskExecutor 生成内容
  - kind=human → 占位（return {"status":"waiting_human", ...}），由 risk_approval 步骤接管

参数注入约定：tool 节点在 plan generation 阶段由模型输出
  binding: "<tool_id>"
  description 或元数据里说明参数来源，例如：
    "args_from: <upstream_node_id>.<field>"
  或硬编码 "args: {employee_id: E001}"

公共入口：
  - aexecute_plan(plan, *, initial_inputs)：异步版本，供 FastAPI / 流式路径使用
  - execute_plan(plan, *, initial_inputs)：同步包装，仅在没有运行中事件循环时可用
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from ..core import GLOBAL_REGISTRY, Plan, TaskExecutor, topological_order
from ..providers import ChatMessage


async def aexecute_plan(
    plan: Plan,
    *,
    initial_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """异步执行整个 Plan。返回各节点结果的 dict。

    initial_inputs 用于把"用户原始 query + 元信息"暴露给 tool/llm 节点。
    """
    order = topological_order(plan)
    results: dict[str, Any] = {"__initial__": initial_inputs or {}}
    executor = TaskExecutor()

    for node in order:
        try:
            if node.kind == "tool":
                args = _resolve_tool_args(node, results)
                obs = await GLOBAL_REGISTRY.execute(node.binding, **args)
                results[node.id] = {"status": "ok", "observation": obs, "args_used": args}
            elif node.kind == "llm":
                prompt = node.binding or node.title
                upstream = _upstream_results(node, results)
                full_prompt = (
                    prompt
                    if not upstream
                    else f"{prompt}\n\n## 上游输入\n{json.dumps(upstream, ensure_ascii=False, indent=2, default=str)[:4000]}"
                )
                content = await asyncio.to_thread(
                    executor.run_text,
                    [ChatMessage(role="user", content=full_prompt)],
                    temperature=0.4,
                )
                results[node.id] = {"status": "ok", "content": content}
            elif node.kind == "human":
                results[node.id] = {"status": "waiting_human", "note": node.title}
            else:
                results[node.id] = {"status": "error", "error": f"unknown kind: {node.kind}"}
        except Exception as exc:  # noqa: BLE001
            results[node.id] = {"status": "error", "error": str(exc), "node": node.title}
    return results


def execute_plan(
    plan: Plan,
    *,
    initial_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同步包装。**禁止在已运行的事件循环里调用**——这种场景应直接 await aexecute_plan。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(aexecute_plan(plan, initial_inputs=initial_inputs))
    raise RuntimeError(
        "execute_plan() cannot be called from a running event loop; "
        "await aexecute_plan(...) instead."
    )


def _resolve_tool_args(node: Any, results: dict[str, Any]) -> dict[str, Any]:
    """根据 node.description 解析 tool 参数。

    支持三种约定：
      1) "args: {json}"           → 直接取 json 当参数
      2) "args_from: query.employee_id"  → 从 initial_inputs.query 抽取
      3) 不带约定                → 默认 {}（工具无参数）
    """
    desc = node.description or ""
    # 1) 显式 args: {...}
    m = re.search(r"args:\s*(\{.*?\})", desc, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 2) args_from: <source>.<field>
    m2 = re.search(r"args_from:\s*([\w.]+)", desc)
    if m2:
        path = m2.group(1).split(".")
        cur: Any = results
        for p in path:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return {}
        if isinstance(cur, str):
            return {"query": cur}
        if isinstance(cur, dict):
            return cur
        return {"value": cur}
    # 3) 默认
    return {}


def _upstream_results(node: Any, results: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for dep in node.depends_on:
        if dep in results:
            out[dep] = results[dep]
    return out


__all__ = ["aexecute_plan", "execute_plan"]
