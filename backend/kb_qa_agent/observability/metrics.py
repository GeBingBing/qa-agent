"""observability/metrics.py — Prometheus 指标定义。

只在 ``prometheus_client`` 可用时启用；缺失时 metrics 端点应返回 503，
不会让业务代码 import 失败。
"""

from __future__ import annotations

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


_REGISTRY = None
_HEALTH_REQUESTS = None
_CHAT_REQUESTS = None
_CHAT_LATENCY = None
_LLM_TOKENS = None


def _init_metrics() -> None:
    global _REGISTRY, _HEALTH_REQUESTS, _CHAT_REQUESTS, _CHAT_LATENCY, _LLM_TOKENS
    if not PROMETHEUS_AVAILABLE or _REGISTRY is not None:
        return
    _REGISTRY = CollectorRegistry()
    _HEALTH_REQUESTS = Counter(
        "kb_qa_health_requests_total",
        "Number of /health requests",
        registry=_REGISTRY,
    )
    _CHAT_REQUESTS = Counter(
        "kb_qa_chat_requests_total",
        "Number of /v1/chat requests",
        ["status", "provider"],
        registry=_REGISTRY,
    )
    _CHAT_LATENCY = Histogram(
        "kb_qa_chat_latency_seconds",
        "End-to-end /v1/chat latency",
        registry=_REGISTRY,
    )
    _LLM_TOKENS = Counter(
        "kb_qa_llm_tokens_total",
        "LLM token usage",
        ["provider", "direction"],
        registry=_REGISTRY,
    )


def record_health() -> None:
    _init_metrics()
    if _HEALTH_REQUESTS is not None:
        _HEALTH_REQUESTS.inc()


def record_chat(status: str, provider: str, duration_seconds: float) -> None:
    _init_metrics()
    if _CHAT_REQUESTS is not None:
        _CHAT_REQUESTS.labels(status=status, provider=provider).inc()
    if _CHAT_LATENCY is not None:
        _CHAT_LATENCY.observe(duration_seconds)


def record_tokens(provider: str, direction: str, count: int) -> None:
    _init_metrics()
    if _LLM_TOKENS is not None:
        _LLM_TOKENS.labels(provider=provider, direction=direction).inc(count)


def render_prometheus_payload() -> tuple[bytes, str]:
    """返回 (payload, content_type)。"""
    if not PROMETHEUS_AVAILABLE:
        raise RuntimeError("prometheus_client is not installed")
    _init_metrics()
    return generate_latest(_REGISTRY), CONTENT_TYPE_LATEST


__all__ = [
    "PROMETHEUS_AVAILABLE",
    "CONTENT_TYPE_LATEST",
    "record_health",
    "record_chat",
    "record_tokens",
    "render_prometheus_payload",
]
