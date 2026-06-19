"""测试 SkillLoader — frontmatter 解析、信任门、必选 Skills。

不调 LLM，只测纯逻辑（select_by_model 留给集成测试用 mock provider）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kb_qa_agent.core.skill_loader import (
    DecisionCard,
    apply_trust_gate,
    load_decision_cards,
    select_required,
)


# ---------------------------------------------------------------------------
# Frontmatter 解析
# ---------------------------------------------------------------------------


def _write_skill(skill_dir: Path, name: str, frontmatter_extra: str = "") -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\n"
        f"name: {name}\n"
        f"description: A test skill named {name}\n"
        f"{frontmatter_extra}"
        f"---\n\n"
        f"# {name}\n\nbody",
        encoding="utf-8",
    )


def test_load_returns_empty_for_missing_dir(tmp_path: Path):
    cards = load_decision_cards(tmp_path / "nonexistent")
    assert cards == []


def test_load_skips_dir_without_skill_md(tmp_path: Path):
    (tmp_path / "not-a-skill").mkdir()
    cards = load_decision_cards(tmp_path)
    assert cards == []


def test_load_parses_basic_frontmatter(tmp_path: Path):
    _write_skill(tmp_path / "my-skill", "my-skill")
    cards = load_decision_cards(tmp_path)
    assert len(cards) == 1
    c = cards[0]
    assert c.skill_id == "my-skill"
    assert c.name == "my-skill"
    assert "test skill" in c.description.lower()


def test_load_parses_metadata(tmp_path: Path):
    _write_skill(
        tmp_path / "skill-with-meta",
        "skill-with-meta",
        frontmatter_extra=(
            "metadata:\n"
            "  domain: hr\n"
            "  trust_level: review\n"
            "  install_source: marketplace\n"
        ),
    )
    cards = load_decision_cards(tmp_path)
    assert len(cards) == 1
    assert cards[0].domain == "hr"
    assert cards[0].trust_level == "review"
    assert cards[0].install_source == "marketplace"


def test_load_multiple_skills(tmp_path: Path):
    _write_skill(tmp_path / "a", "a")
    _write_skill(tmp_path / "b", "b")
    _write_skill(tmp_path / "c", "c")
    cards = load_decision_cards(tmp_path)
    assert len(cards) == 3
    assert {c.skill_id for c in cards} == {"a", "b", "c"}


def test_load_extracts_keywords(tmp_path: Path):
    """name + description 应被切成关键词（中英文）。"""
    _write_skill(
        tmp_path / "leave-tool",
        "leave-tool",
        frontmatter_extra="metadata:\n  keywords:\n    - vacation\n    - 年假\n",
    )
    cards = load_decision_cards(tmp_path)
    assert len(cards) == 1
    # 显式 keywords 字段应该被吸收
    assert "vacation" in cards[0].keywords or "leave" in cards[0].keywords


# ---------------------------------------------------------------------------
# select_required
# ---------------------------------------------------------------------------


def test_select_required_returns_matching_cards():
    cards = [
        DecisionCard(skill_id="a", name="a", description=""),
        DecisionCard(skill_id="b", name="b", description=""),
    ]
    passed, rejected = select_required(["a"], cards)
    assert len(passed) == 1
    assert passed[0].skill_id == "a"
    assert rejected == []


def test_select_required_reports_missing():
    cards = [DecisionCard(skill_id="a", name="a", description="")]
    passed, rejected = select_required(["a", "ghost"], cards)
    assert len(passed) == 1
    assert len(rejected) == 1
    assert rejected[0]["skill_id"] == "ghost"
    assert rejected[0]["reason"] == "required_not_found"


def test_select_required_empty_input():
    cards = [DecisionCard(skill_id="a", name="a", description="")]
    passed, rejected = select_required([], cards)
    assert passed == []
    assert rejected == []


# ---------------------------------------------------------------------------
# apply_trust_gate
# ---------------------------------------------------------------------------


def test_trust_gate_passes_trusted_card():
    cards = [
        DecisionCard(
            skill_id="t",
            name="t",
            description="",
            install_source="builtin",
            trust_level="trusted",
        ),
    ]
    decision = apply_trust_gate(cards)
    assert len(decision.passed) == 1
    assert decision.blocked == []


def test_trust_gate_blocks_blocked_card():
    cards = [
        DecisionCard(
            skill_id="b",
            name="b",
            description="",
            install_source="third_party",
            trust_level="blocked",
        ),
    ]
    decision = apply_trust_gate(cards)
    assert decision.passed == []
    assert len(decision.blocked) == 1
    assert decision.blocked[0][0].skill_id == "b"
    assert decision.blocked[0][1] == "trust_level_blocked"


def test_trust_gate_review_level_passes():
    cards = [
        DecisionCard(
            skill_id="r",
            name="r",
            description="",
            install_source="marketplace",
            trust_level="review",
        ),
    ]
    decision = apply_trust_gate(cards)
    # review 是"放行但需复核"，不阻断
    assert len(decision.passed) == 1
    assert decision.blocked == []


def test_trust_gate_uses_install_source_when_no_card_level():
    """card.trust_level 为空时按 install_source → trust_level 映射。"""
    cards = [
        DecisionCard(
            skill_id="m",
            name="m",
            description="",
            install_source="third_party",
            trust_level="",  # 空 → 看 install_source 映射
        ),
    ]
    config = {
        "builtin": "trusted",
        "marketplace": "review",
        "local": "trusted",
        "third_party": "blocked",
    }
    decision = apply_trust_gate(cards, trust_config=config)
    assert decision.passed == []
    assert len(decision.blocked) == 1


def test_trust_gate_empty_cards():
    decision = apply_trust_gate([])
    assert decision.passed == []
    assert decision.blocked == []
