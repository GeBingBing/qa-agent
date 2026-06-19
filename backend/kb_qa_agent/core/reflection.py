"""reflection.py — 反思循环（Draft → Evaluate → Revise 模式）。

输入：初稿 + 评估标准；输出：(是否通过, 评估意见)
通过则退出；不通过则让模型基于意见重写，最多 max_rounds 轮。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..providers import ChatMessage
from .model_request import TaskExecutor


EVAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "score": {"type": "number", "description": "0-1, overall quality"},
        "issues": {"type": "array", "items": {"type": "string"}, "description": "Specific issues with the draft"},
        "suggestions": {"type": "array", "items": {"type": "string"}, "description": "Concrete suggestions for improvement"},
    },
    "required": ["passed", "score", "issues", "suggestions"],
}


DEFAULT_REPORT_CRITERIA = [
    "准确性：是否与检索到的政策文档一致，无虚构事实",
    "完整性：是否覆盖用户问题的所有子问题",
    "可执行性：是否给出明确的下一步操作（如适用）",
    "引用：当涉及具体条款时是否注明来源",
    "风险提示：是否存在合规 / 法律 / 数据安全风险被忽略",
]


@dataclass
class EvaluationResult:
    passed: bool
    score: float
    issues: list[str]
    suggestions: list[str]


def evaluate_draft(draft: str, criteria: list[str], *, context: str = "") -> EvaluationResult:
    """让模型评估草稿。"""
    crit_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(criteria))
    user_prompt = (
        f"## 评估标准\n{crit_text}\n\n"
        f"## 上下文\n{context or '(无)'}\n\n"
        f"## 待评估草稿\n{draft}\n\n"
        "请严格按 JSON Schema 输出评估结论。"
    )
    raw = TaskExecutor().run_structured(
        [ChatMessage(role="user", content=user_prompt)],
        schema=EVAL_SCHEMA,
        temperature=0.1,
    )
    return EvaluationResult(
        passed=bool(raw.get("passed", False)),
        score=float(raw.get("score", 0.0)),
        issues=list(raw.get("issues", []) or []),
        suggestions=list(raw.get("suggestions", []) or []),
    )


def revise_draft(draft: str, evaluation: EvaluationResult, *, context: str = "") -> str:
    """让模型基于评估意见改写草稿。"""
    issues_text = "\n".join(f"- {i}" for i in evaluation.issues) or "(none)"
    sug_text = "\n".join(f"- {s}" for s in evaluation.suggestions) or "(none)"
    user_prompt = (
        f"## 上一轮评估\n问题：\n{issues_text}\n\n建议：\n{sug_text}\n\n"
        f"## 上下文\n{context or '(无)'}\n\n"
        f"## 待改写草稿\n{draft}\n\n"
        "请基于以上意见重写。要求：保持专业语气；修正所有问题；直接输出改写后的正文，"
        "不要 JSON，不要前缀说明，不要围栏。"
    )
    return TaskExecutor().run_text(
        [ChatMessage(role="user", content=user_prompt)],
        temperature=0.4,
    )


def reflect_and_revise(
    draft: str,
    *,
    context: str = "",
    criteria: list[str] | None = None,
    max_rounds: int = 2,
    score_threshold: float = 0.85,
) -> tuple[str, list[EvaluationResult], int]:
    """反思循环主体。返回 (最终草稿, 评估历史, 总轮数)。"""
    crit = criteria or DEFAULT_REPORT_CRITERIA
    evaluations: list[EvaluationResult] = []
    current = draft
    rounds = 0
    for i in range(max_rounds):
        rounds = i + 1
        ev = evaluate_draft(current, crit, context=context)
        evaluations.append(ev)
        if ev.passed or ev.score >= score_threshold:
            break
        current = revise_draft(current, ev, context=context)
    return current, evaluations, rounds


__all__ = [
    "EvaluationResult",
    "evaluate_draft",
    "revise_draft",
    "reflect_and_revise",
    "DEFAULT_REPORT_CRITERIA",
    "EVAL_SCHEMA",
]
