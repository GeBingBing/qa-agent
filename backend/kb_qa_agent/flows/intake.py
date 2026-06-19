"""flows/intake.py — 入口分类（用户问题 → domain / intent / confidence）。"""

from __future__ import annotations

from typing import Any

from ..core import route_query


def classify_intent(user_query: str, *, conversation_history: list[dict] | None = None) -> dict[str, Any]:
    """用户问题 → {domain, intent, confidence, reasoning, needs_tools}"""
    return route_query(user_query, conversation_history=conversation_history)


__all__ = ["classify_intent"]
