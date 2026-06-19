"""测试 reflection 循环（P2-7）。

期望：
  - 第一轮 passed=True 时立即返回，rounds=1
  - 第一轮 score 已超阈值，也立即返回
  - 否则进入 revise → 重新 evaluate，最多 max_rounds 轮
"""

from __future__ import annotations

import pytest
from kb_qa_agent.core.reflection import (
    EvaluationResult,
    reflect_and_revise,
)


@pytest.fixture
def stub_eval_revise(monkeypatch):
    """注入可编排的 evaluate / revise stub。"""
    from kb_qa_agent.core import reflection as ref_mod

    eval_queue: list[EvaluationResult] = []
    revise_calls: list[tuple[str, EvaluationResult]] = []

    def fake_eval(draft, criteria, *, context=""):
        return eval_queue.pop(0) if eval_queue else EvaluationResult(True, 1.0, [], [])

    def fake_revise(draft, evaluation, *, context=""):
        revise_calls.append((draft, evaluation))
        return draft + " [revised]"

    monkeypatch.setattr(ref_mod, "evaluate_draft", fake_eval)
    monkeypatch.setattr(ref_mod, "revise_draft", fake_revise)
    return eval_queue, revise_calls


def test_passed_first_round_returns_immediately(stub_eval_revise):
    eval_queue, revise_calls = stub_eval_revise
    eval_queue.append(EvaluationResult(passed=True, score=0.9, issues=[], suggestions=[]))
    final, evals, rounds = reflect_and_revise("draft", max_rounds=2)
    assert final == "draft"
    assert rounds == 1
    assert len(evals) == 1
    assert revise_calls == []


def test_score_above_threshold_short_circuits(stub_eval_revise):
    eval_queue, revise_calls = stub_eval_revise
    eval_queue.append(EvaluationResult(passed=False, score=0.9, issues=["x"], suggestions=["y"]))
    final, evals, rounds = reflect_and_revise("draft", max_rounds=3, score_threshold=0.85)
    assert final == "draft"
    assert rounds == 1
    assert revise_calls == []


def test_loops_until_max_rounds(stub_eval_revise):
    eval_queue, revise_calls = stub_eval_revise
    eval_queue.extend([
        EvaluationResult(passed=False, score=0.5, issues=["a"], suggestions=["b"]),
        EvaluationResult(passed=False, score=0.6, issues=["c"], suggestions=["d"]),
    ])
    final, evals, rounds = reflect_and_revise("draft", max_rounds=2)
    assert rounds == 2
    # 第 1 轮：evaluate(draft) 失败 → revise → "draft [revised]"
    # 第 2 轮：evaluate("draft [revised]") 失败 → revise → "draft [revised] [revised]"
    assert final == "draft [revised] [revised]"
    assert len(revise_calls) == 2
    assert len(evals) == 2
