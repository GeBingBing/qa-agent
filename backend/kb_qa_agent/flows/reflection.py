"""flows/reflection.py — 反思迭代并生成最终回答。"""

from __future__ import annotations

from typing import Any

from ..core import DEFAULT_REPORT_CRITERIA, reflect_and_revise


def finalize_with_reflection(
    draft: str,
    *,
    context: str = "",
    criteria: list[str] | None = None,
    max_rounds: int = 2,
) -> dict[str, Any]:
    """对草稿做反思迭代。返回最终稿 + 评估历史。"""
    final, evaluations, rounds = reflect_and_revise(
        draft,
        context=context,
        criteria=criteria or DEFAULT_REPORT_CRITERIA,
        max_rounds=max_rounds,
    )
    return {
        "final_answer": final,
        "evaluations": [
            {
                "passed": ev.passed,
                "score": ev.score,
                "issues": ev.issues,
                "suggestions": ev.suggestions,
            }
            for ev in evaluations
        ],
        "rounds": rounds,
    }


__all__ = ["finalize_with_reflection"]
