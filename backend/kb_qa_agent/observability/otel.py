"""observability/otel.py — 可选 OpenTelemetry exporter。

设计：
  - 默认关闭。仅当 ``OTEL_EXPORTER_OTLP_ENDPOINT`` 被设置时才尝试启用
  - SDK / OTLP exporter 不可用时 logger.warning 后降级，不阻塞应用
  - 成功后注册全局 TracerProvider + BatchSpanProcessor，剩下让用户的 OTel
    生态（Jaeger / Tempo / Grafana / OpenObserve…）自行接收

main.py 会在 lifespan 启动时调一次。
"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger("kb_qa_agent.observability.otel")


_INSTALLED: bool = False


def _reset_for_tests() -> None:
    global _INSTALLED
    _INSTALLED = False


def is_installed() -> bool:
    return _INSTALLED


def _load_sdk() -> Any | None:
    """加载 opentelemetry sdk + OTLP exporter。失败返回 None。"""
    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.debug("opentelemetry sdk not importable: %s", exc)
        return None

    return SimpleNamespace(
        TracerProvider=TracerProvider,
        BatchSpanProcessor=BatchSpanProcessor,
        OTLPSpanExporter=OTLPSpanExporter,
        Resource=Resource,
        set_global_provider=trace.set_tracer_provider,
    )


def install_otel_if_enabled() -> bool:
    """根据环境变量按需启用 OTel。返回是否实际装好。"""
    global _INSTALLED
    if _INSTALLED:
        return True

    endpoint = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint:
        return False

    sdk = _load_sdk()
    if sdk is None:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but opentelemetry SDK / OTLP exporter "
            "is not installed; tracing falls back to local JSONL only. "
            "Install opentelemetry-sdk + opentelemetry-exporter-otlp-proto-http to enable."
        )
        return False

    service_name = (os.environ.get("OTEL_SERVICE_NAME") or "kb-qa-agent").strip()
    resource = sdk.Resource.create({"service.name": service_name})
    provider = sdk.TracerProvider(resource=resource)
    exporter = sdk.OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(sdk.BatchSpanProcessor(exporter))
    sdk.set_global_provider(provider)

    logger.info("opentelemetry exporter enabled: endpoint=%s service=%s", endpoint, service_name)
    _INSTALLED = True
    return True


__all__ = ["install_otel_if_enabled", "is_installed"]
