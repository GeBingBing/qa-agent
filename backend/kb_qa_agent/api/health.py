"""api/health.py — 健康检查 / 元信息端点。"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from ..providers import active_provider, list_available
from ..core import GLOBAL_REGISTRY, load_decision_cards
from ..observability import metrics as metrics_mod
from .models import HealthResponse


router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    metrics_mod.record_health()
    name, _ = active_provider()
    return HealthResponse(
        status="ok",
        active_provider=name,
        available_providers=list_available(),
        total_tools=len(GLOBAL_REGISTRY.list()),
        skills_loaded=len(load_decision_cards()),
    )


@router.get("/health/ready")
async def health_ready(response: Response) -> dict:
    """就绪探针：检查 active provider 是否已配置。"""
    name, provider = active_provider()
    provider_ok = provider.available()
    checks = {
        "active_provider": {
            "ok": provider_ok,
            "name": name,
            "available_others": list_available(),
        },
    }
    overall_ok = provider_ok
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if overall_ok else "not_ready", "checks": checks}


@router.get("/metrics")
async def metrics() -> Response:
    if not metrics_mod.PROMETHEUS_AVAILABLE:
        return Response(
            content="prometheus_client not installed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="text/plain; charset=utf-8",
        )
    payload, content_type = metrics_mod.render_prometheus_payload()
    return Response(content=payload, media_type=content_type)


@router.get("/v1/tools")
async def list_tools():
    """列出所有已注册的工具（按 domain 分组）。"""
    out: dict[str, list[dict]] = {}
    for spec in GLOBAL_REGISTRY.list():
        out.setdefault(spec.domain or "general", []).append({
            "id": spec.id,
            "desc": spec.desc,
            "side_effect_level": spec.side_effect_level,
            "input_schema": spec.input_schema,
        })
    return out


@router.get("/v1/skills")
async def list_skills():
    """列出所有加载的 Skills 摘要。"""
    cards = load_decision_cards()
    return [
        {
            "skill_id": c.skill_id,
            "name": c.name,
            "description": c.description,
            "domain": c.domain,
            "trust_level": c.trust_level,
            "install_source": c.install_source,
        }
        for c in cards
    ]
