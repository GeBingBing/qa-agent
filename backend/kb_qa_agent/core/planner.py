"""planner.py — DAG 任务规划。

能力：
  1. 模型生成 DAG（节点 / 依赖 / 类型）
  2. 拓扑排序校验（Kahn 算法）
  3. 校验失败时回灌错误让模型自我修正（plan_with_retry）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..providers import ChatMessage
from .model_request import TaskExecutor

NodeKind = Literal["llm", "tool", "human"]


@dataclass
class PlanNode:
    id: str
    kind: NodeKind
    title: str
    description: str = ""
    binding: str = ""               # tool 节点的 tool_id；llm 节点的子任务说明
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 1


@dataclass
class Plan:
    rationale: str
    nodes: list[PlanNode]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rationale": self.rationale,
            "nodes": [
                {**n.__dict__}
                for n in self.nodes
            ],
        }


class PlannerError(Exception):
    pass


PLANNER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique snake_case node id"},
                    "kind": {"type": "string", "description": "One of llm / tool / human"},
                    "title": {"type": "string", "description": "Short human-readable title"},
                    "description": {"type": "string", "description": "What this node does in 1-2 sentences"},
                    "binding": {"type": "string", "description": "For kind=tool: the tool id. For kind=llm: a brief prompt describing what to generate. Empty for kind=human."},
                    "depends_on": {"type": "array", "items": {"type": "string"}, "description": "List of upstream node ids"},
                    "max_retries": {"type": "integer", "description": "Retry count on failure; 0 = no retry"},
                },
                "required": ["id", "kind", "title"],
            },
        },
    },
    "required": ["rationale", "nodes"],
}


PLANNER_SYSTEM = """你是一个任务规划器。

输入：用户的原始问题 + 上下文（领域 / 已命中 Skills / 可用工具列表）。
输出：一个严格 JSON 描述的执行 DAG。

规则：
  1. 节点用 snake_case id（必须唯一）
  2. kind 只能是 llm / tool / human 之一
     - llm：让大模型生成内容；binding 是具体指令
     - tool：调用一个工具；binding 是 tool id
     - human：等待人工审批；binding 留空
  3. depends_on 列出的 id 必须是其它节点的 id；可空
  4. 整体必须是有向无环图（DAG）；如有环请改写
  5. 节点数量控制在 3-8 个；不要拆得过细
  6. 第一个节点通常是 tool 或 llm（fetch 数据），最后一个节点是 llm（finalize）
"""


def plan_dag(
    user_query: str,
    *,
    domain: str,
    available_tools: list[str] | None = None,
    selected_skills: list[str] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> Plan:
    """调模型生成 DAG 计划。"""
    msgs: list[ChatMessage] = [
        ChatMessage(role="system", content=PLANNER_SYSTEM),
        ChatMessage(role="user", content=_build_user_prompt(
            user_query, domain=domain, available_tools=available_tools or [],
            selected_skills=selected_skills or [], extra_context=extra_context or {},
        )),
    ]
    raw = TaskExecutor().run_structured(msgs, schema=PLANNER_SCHEMA, temperature=0.2)
    return _parse_plan(raw)


def plan_with_retry(
    user_query: str,
    *,
    domain: str,
    available_tools: list[str] | None = None,
    selected_skills: list[str] | None = None,
    extra_context: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> Plan:
    """生成 → 校验 → 失败则把错误回灌给模型 → 重试。"""
    last_err: Exception | None = None
    for _attempt in range(max_retries):
        try:
            msgs: list[ChatMessage] = [
                ChatMessage(role="system", content=PLANNER_SYSTEM),
                ChatMessage(role="user", content=_build_user_prompt(
                    user_query, domain=domain,
                    available_tools=available_tools or [],
                    selected_skills=selected_skills or [],
                    extra_context=extra_context or {},
                )),
            ]
            if last_err is not None:
                msgs.append(ChatMessage(role="user", content=(
                    f"上一轮的输出未能通过校验：{last_err}\n"
                    "请重新规划，注意以上错误并修正。"
                )))
            raw = TaskExecutor().run_structured(msgs, schema=PLANNER_SCHEMA, temperature=0.2)
            plan = _parse_plan(raw)
            validate_plan(plan)
            return plan
        except PlannerError as exc:
            last_err = exc
    raise PlannerError(f"Failed to produce a valid plan after {max_retries} attempts: {last_err}")


def validate_plan(plan: Plan) -> None:
    """校验 Plan：唯一 id / 依赖存在 / 无环。"""
    ids = {n.id for n in plan.nodes}
    if len(ids) != len(plan.nodes):
        raise PlannerError("Plan contains duplicate node ids")
    # 校验 depends_on 引用的 id 都存在
    for n in plan.nodes:
        for dep in n.depends_on:
            if dep not in ids:
                raise PlannerError(f"Node {n.id!r} depends on unknown node {dep!r}")
            if dep == n.id:
                raise PlannerError(f"Node {n.id!r} depends on itself")
    # Kahn 拓扑排序检测环
    in_degree: dict[str, int] = {n.id: 0 for n in plan.nodes}
    children: dict[str, list[str]] = {n.id: [] for n in plan.nodes}
    for n in plan.nodes:
        for dep in n.depends_on:
            in_degree[n.id] += 1
            children[dep].append(n.id)
    queue = [nid for nid, d in in_degree.items() if d == 0]
    visited = 0
    while queue:
        nid = queue.pop(0)
        visited += 1
        for c in children[nid]:
            in_degree[c] -= 1
            if in_degree[c] == 0:
                queue.append(c)
    if visited != len(plan.nodes):
        raise PlannerError("Plan contains a dependency cycle")


def topological_order(plan: Plan) -> list[PlanNode]:
    """返回拓扑顺序的节点列表。"""
    validate_plan(plan)
    in_degree: dict[str, int] = {n.id: 0 for n in plan.nodes}
    children: dict[str, list[str]] = {n.id: [] for n in plan.nodes}
    by_id = {n.id: n for n in plan.nodes}
    for n in plan.nodes:
        for dep in n.depends_on:
            in_degree[n.id] += 1
            children[dep].append(n.id)
    queue = [by_id[nid] for nid, d in in_degree.items() if d == 0]
    out: list[PlanNode] = []
    while queue:
        node = queue.pop(0)
        out.append(node)
        for c in children[node.id]:
            in_degree[c] -= 1
            if in_degree[c] == 0:
                queue.append(by_id[c])
    return out


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_plan(raw: dict[str, Any]) -> Plan:
    nodes = []
    for item in raw.get("nodes", []):
        kind = str(item.get("kind", "llm")).strip().lower()
        if kind not in ("llm", "tool", "human"):
            raise PlannerError(f"Invalid node kind: {kind!r}")
        nodes.append(PlanNode(
            id=item["id"],
            kind=kind,
            title=item["title"],
            description=item.get("description", ""),
            binding=item.get("binding", ""),
            depends_on=list(item.get("depends_on", []) or []),
            max_retries=int(item.get("max_retries", 1)),
        ))
    return Plan(rationale=raw.get("rationale", ""), nodes=nodes)


def _build_user_prompt(query, *, domain, available_tools, selected_skills, extra_context):
    parts = [
        f"## 用户问题\n{query}",
        f"## 所属领域\n{domain}",
    ]
    if available_tools:
        parts.append("## 可用工具\n" + "\n".join(f"- {t}" for t in available_tools))
    if selected_skills:
        parts.append("## 已命中 Skills\n" + "\n".join(f"- {s}" for s in selected_skills))
    if extra_context:
        parts.append("## 额外上下文\n" + str(extra_context))
    parts.append("\n请输出符合 schema 的 JSON。")
    return "\n\n".join(parts)


__all__ = ["PlanNode", "Plan", "PlannerError", "plan_dag", "plan_with_retry", "validate_plan", "topological_order"]
