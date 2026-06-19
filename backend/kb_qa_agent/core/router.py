"""router.py — 意图路由（基于 schema 强约束的 LLM 分类器）。

把用户 query 分到 4 个 domain + 子意图：
  - hr
  - finance
  - it
  - legal
  - general  (闲聊/超出范围)

用 TaskExecutor.structured + schema 强制 JSON 输出。
"""

from __future__ import annotations

from typing import Any, Literal

from ..providers import ChatMessage
from .model_request import TaskExecutor


DomainName = Literal["hr", "finance", "it", "legal", "general"]


ROUTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "description": "One of hr / finance / it / legal / general",
        },
        "intent": {
            "type": "string",
            "description": "Free-form intent within the chosen domain (e.g. leave_inquiry, expense_policy, account_permission)",
        },
        "confidence": {
            "type": "number",
            "description": "Confidence between 0 and 1",
        },
        "reasoning": {
            "type": "string",
            "description": "One-sentence explanation of why this domain was chosen",
        },
        "needs_tools": {
            "type": "boolean",
            "description": "Whether the answer requires looking up internal data (True) or can be answered from policies alone (False)",
        },
    },
    "required": ["domain", "intent", "confidence", "reasoning", "needs_tools"],
}


_ROUTER_SYSTEM = """你是一个企业内部知识库的意图路由器。

任务：阅读用户的提问，分类到以下 5 个领域之一：
  - hr       人事：请假、考勤、薪酬、合同、离职、入职、社保
  - finance  财务：报销、预算、付款、发票、成本
  - it       IT：账号、权限、系统故障、VPN、设备申请、工单状态
  - legal    法务：合同条款、合规审查、知识产权、政策法规
  - general  闲聊或不在上述 4 个领域

要求：
  - 必须输出严格符合 JSON Schema 的 JSON
  - confidence 反映你的判断确信度；不确定时宁可降到 0.5
  - reasoning 用一句话解释分类理由
  - needs_tools: 这个问题是否需要调用内部数据查询工具（如查假期余额、查工单状态），
    还是可以直接从政策文档回答
"""


def route_query(user_query: str, *, conversation_history: list[dict] | None = None) -> dict[str, Any]:
    """对用户 query 做意图路由。

    Returns: dict matching ROUTER_SCHEMA, plus injected ``domain`` field normalized
    to one of the 5 valid values.
    """
    history = conversation_history or []
    msgs: list[ChatMessage] = [ChatMessage(role="system", content=_ROUTER_SYSTEM)]
    for h in history[-6:]:   # 最近 3 轮
        msgs.append(ChatMessage(
            role=h.get("role", "user"),
            content=h.get("content", ""),
        ))
    msgs.append(ChatMessage(role="user", content=user_query))

    raw = TaskExecutor().run_structured(msgs, schema=ROUTER_SCHEMA, temperature=0.1)

    # 强制 domain 合法
    domain = str(raw.get("domain", "general")).strip().lower()
    if domain not in {"hr", "finance", "it", "legal", "general"}:
        domain = "general"
    raw["domain"] = domain

    return raw


__all__ = ["route_query", "ROUTER_SCHEMA", "DomainName"]
