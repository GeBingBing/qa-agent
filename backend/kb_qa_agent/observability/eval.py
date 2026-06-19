"""observability/eval.py — eval_harness 入口。

外部调用见 backend/eval/run_eval.py；本模块提供评分原语。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EvalSample:
    question: str
    expected_keywords: list[str]
    expected_domain: str = ""
    expected_risk: str = ""
    forbidden_phrases: list[str] | None = None


@dataclass
class EvalResult:
    sample: EvalSample
    actual_answer: str
    actual_domain: str
    actual_risk: str
    keyword_recall: float
    keyword_hits: list[str]
    keyword_misses: list[str]
    contains_forbidden: bool
    passed: bool


def score_answer(sample: EvalSample, answer: str, *, actual_domain: str = "", actual_risk: str = "") -> EvalResult:
    """给一个 (sample, answer) 打分。"""
    lower = answer.lower()
    hits = [k for k in sample.expected_keywords if k.lower() in lower]
    misses = [k for k in sample.expected_keywords if k.lower() not in lower]
    recall = len(hits) / max(1, len(sample.expected_keywords))
    forbidden_hit = False
    for p in sample.forbidden_phrases or []:
        if p.lower() in lower:
            forbidden_hit = True
            break
    domain_ok = (not sample.expected_domain) or sample.expected_domain == actual_domain
    risk_ok = (not sample.expected_risk) or sample.expected_risk == actual_risk
    passed = (recall >= 0.7) and (not forbidden_hit) and domain_ok and risk_ok
    return EvalResult(
        sample=sample,
        actual_answer=answer,
        actual_domain=actual_domain,
        actual_risk=actual_risk,
        keyword_recall=recall,
        keyword_hits=hits,
        keyword_misses=misses,
        contains_forbidden=forbidden_hit,
        passed=passed,
    )


__all__ = ["EvalSample", "EvalResult", "score_answer"]
