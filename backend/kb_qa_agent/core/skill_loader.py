"""skill_loader.py — Skills 加载 / 选择 / 信任门。

API 三件套：
  load_decision_cards(skills_dir) -> list[DecisionCard]
  select_skills(query, cards, *, mode='auto') -> list[DecisionCard]   # mode: auto / required
  apply_trust_gate(cards, trust_config) -> (passed, blocked)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore

from ..config import get_config
from ..providers import ChatMessage
from .model_request import TaskExecutor


# ---------------------------------------------------------------------------
# DecisionCard
# ---------------------------------------------------------------------------


@dataclass
class DecisionCard:
    skill_id: str          # 唯一 id，来自 frontmatter 的 name 字段
    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    install_source: Literal["builtin", "marketplace", "local", "third_party"] = "builtin"
    trust_level: Literal["trusted", "review", "blocked"] = "trusted"
    domain: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    m = _FRONTMATTER_RE.search(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _extract_keywords(name: str, description: str) -> list[str]:
    """从 name + description 提取关键词。中文按字切（粗略）。"""
    text = (name + " " + description).lower()
    keywords: set[str] = set()
    # 英文单词
    for w in re.findall(r"[a-z_]{3,}", text):
        keywords.add(w)
    # 中文 2-gram
    cjk = re.findall(r"[一-鿿]+", text)
    for s in cjk:
        for i in range(len(s) - 1):
            keywords.add(s[i : i + 2])
    return sorted(keywords)


def load_decision_cards(skills_dir: str | Path | None = None) -> list[DecisionCard]:
    """扫描 skills_dir 下所有 */SKILL.md，提取 frontmatter 生成 DecisionCard."""
    cfg = get_config()
    if skills_dir is not None:
        base = Path(skills_dir).resolve()
    else:
        # 默认相对包路径（最稳），SETTINGS.yaml 显式给绝对路径才用
        default = Path(__file__).resolve().parents[1] / "skills"
        cfg_dir = cfg.get("skills", {}).get("base_dir", "") or ""
        if cfg_dir and Path(cfg_dir).is_absolute():
            base = Path(cfg_dir).resolve()
        else:
            base = default.resolve()
    if not base.exists():
        return []
    cards: list[DecisionCard] = []
    for skill_md in sorted(base.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if not fm:
            continue
        name = fm.get("name") or skill_md.parent.name
        desc = fm.get("description", "")
        metadata = fm.get("metadata") or {}
        install_source = metadata.get("install_source", "builtin")
        trust_level = metadata.get("trust_level", "trusted")
        domain = metadata.get("domain", "")
        # 提取额外的关键词字段（如果有）
        extra_keywords = list(metadata.get("keywords", []) or [])
        all_keywords = sorted(set(_extract_keywords(name, desc) + [str(k).lower() for k in extra_keywords]))
        cards.append(DecisionCard(
            skill_id=name,
            name=name,
            description=desc,
            keywords=all_keywords,
            install_source=install_source,
            trust_level=trust_level,
            domain=domain,
            extra=metadata,
        ))
    return cards


# ---------------------------------------------------------------------------
# Select — 模型驱动 Skill 选择
# ---------------------------------------------------------------------------


SELECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "priority": {"type": "integer"},
                },
                "required": ["skill_id", "reason", "priority"],
            },
        },
        "rejected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["skill_id", "reason"],
            },
        },
    },
    "required": ["selected", "rejected"],
}


_SELECT_SYSTEM = """你是一个 Skill 选择器。

任务：根据用户问题，从候选 Skill 列表里挑选出真正需要的 Skill。
规则：
  - 只在确实有助于回答问题时才选择（少即是多）
  - selected 按调用顺序排（priority 从小到大）
  - rejected 必须给出明确的不选理由
  - 必须输出严格符合 JSON Schema 的 JSON
"""


def _keyword_prefilter(query: str, cards: list[DecisionCard], max_keep: int = 8) -> list[DecisionCard]:
    """基于关键词预筛，降低 prompt token 消耗。"""
    q_tokens = set(re.findall(r"[a-z_]{3,}", query.lower()))
    q_cjk = set()
    for s in re.findall(r"[一-鿿]+", query):
        for i in range(len(s) - 1):
            q_cjk.add(s[i : i + 2])

    scored: list[tuple[int, DecisionCard]] = []
    for c in cards:
        score = sum(1 for k in c.keywords if k in q_tokens or k in q_cjk)
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] == 0:
        # 没命中 → 全量返回，避免遗漏
        return cards[:max_keep]
    return [c for _, c in scored[:max_keep]]


def select_by_model(query: str, cards: list[DecisionCard]) -> dict[str, Any]:
    """调模型选 Skill。"""
    pool = _keyword_prefilter(query, cards)
    cards_text = "\n\n".join(
        f"- id={c.skill_id}\n  desc={c.description}\n  domain={c.domain}\n  trust={c.trust_level}"
        for c in pool
    )
    user = f"## 用户问题\n{query}\n\n## 候选 Skill\n{cards_text}"
    raw = TaskExecutor().run_structured(
        [ChatMessage(role="system", content=_SELECT_SYSTEM), ChatMessage(role="user", content=user)],
        schema=SELECT_SCHEMA,
        temperature=0.1,
    )
    raw["pool_size"] = len(pool)
    raw["total_cards"] = len(cards)
    return raw


def select_required(skill_ids: list[str], cards: list[DecisionCard]) -> tuple[list[DecisionCard], list[dict[str, str]]]:
    """按 id 硬性选（用于 system prompt 显式要求）。"""
    by_id = {c.skill_id: c for c in cards}
    passed = [by_id[i] for i in skill_ids if i in by_id]
    rejected = [{"skill_id": i, "reason": "required_not_found"} for i in skill_ids if i not in by_id]
    return passed, rejected


# ---------------------------------------------------------------------------
# Trust gate — install_source → trust_level 映射过滤
# ---------------------------------------------------------------------------


@dataclass
class TrustDecision:
    passed: list[DecisionCard]
    blocked: list[tuple[DecisionCard, str]]


def apply_trust_gate(cards: list[DecisionCard], trust_config: dict[str, str] | None = None) -> TrustDecision:
    """根据 install_source → trust_level 映射过滤。"""
    cfg = trust_config or get_config().get("skills", {}).get("trust", {}).get("install_sources", {}) or {
        "builtin": "trusted",
        "marketplace": "review",
        "local": "trusted",
        "third_party": "blocked",
    }
    passed: list[DecisionCard] = []
    blocked: list[tuple[DecisionCard, str]] = []
    for c in cards:
        # 优先级：card 自带的 trust_level > 映射
        level = c.trust_level or cfg.get(c.install_source, "trusted")
        if level == "blocked":
            blocked.append((c, "trust_level_blocked"))
        else:
            passed.append(c)
    return TrustDecision(passed=passed, blocked=blocked)


__all__ = [
    "DecisionCard",
    "load_decision_cards",
    "select_by_model",
    "select_required",
    "apply_trust_gate",
    "TrustDecision",
    "SELECT_SCHEMA",
]
