"""flows/plan_gen.py — 计划生成（RAG + Skill 选择 + DAG 规划三件套）。

整合 RAG + Skill 选择 + Planner 三件事：
  1. 用 RAG 检索政策文档，作为 planner 的额外上下文
  2. 用 SkillLoader 选择相关 Skill
  3. 用 Planner 生成 DAG
"""

from __future__ import annotations

from typing import Any

from ..core import (
    GLOBAL_REGISTRY,
    RAG,
    Plan,
    apply_trust_gate,
    load_decision_cards,
    plan_with_retry,
    select_by_model,
)


def generate_plan(
    user_query: str,
    *,
    domain: str,
    rag: RAG | None = None,
    use_rag: bool = True,
    use_skills: bool = True,
    max_retries: int = 3,
) -> dict[str, Any]:
    """生成执行计划。

    Returns:
        {
          "plan": Plan,
          "rag_hits": [...],
          "selected_skills": [...],
          "blocked_skills": [...],
        }
    """
    rag_hits: list[Any] = []
    selected: list[Any] = []
    blocked: list[Any] = []

    # 1) RAG 检索
    extra_context: dict[str, Any] = {}
    if use_rag and rag is not None and domain != "general":
        try:
            hits = rag.retrieve(user_query, top_k=4, where={"domain": domain} if domain else None)
            rag_hits = hits
            extra_context["rag_chunks"] = [
                {"text": h.text[:500], "source": h.metadata.get("source", "?"), "score": h.score}
                for h in hits
            ]
        except Exception as exc:  # noqa: BLE001
            extra_context["rag_error"] = str(exc)

    # 2) Skill 选择
    if use_skills:
        try:
            cards = load_decision_cards()
            trust = apply_trust_gate(cards)
            usable = trust.passed
            # 只把同 domain 的 skills 注入 plan
            usable_for_domain = [c for c in usable if c.domain == domain] if domain else usable
            decision = select_by_model(user_query, usable_for_domain)
            selected = decision.get("selected", [])
            blocked = trust.blocked
            extra_context["selected_skills"] = [s.get("skill_id") for s in selected]
        except Exception as exc:  # noqa: BLE001
            extra_context["skills_error"] = str(exc)

    # 3) 工具清单注入
    tool_ids = [s.id for s in GLOBAL_REGISTRY.filter(domain=domain)] if domain != "general" else GLOBAL_REGISTRY.list_ids()

    # 4) 生成 DAG
    plan: Plan = plan_with_retry(
        user_query,
        domain=domain,
        available_tools=tool_ids,
        selected_skills=extra_context.get("selected_skills", []),
        extra_context=extra_context,
        max_retries=max_retries,
    )

    return {
        "plan": plan,
        "rag_hits": rag_hits,
        "selected_skills": selected,
        "blocked_skills": blocked,
        "extra_context": extra_context,
    }


__all__ = ["generate_plan"]
