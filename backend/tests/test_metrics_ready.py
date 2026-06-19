"""测试 /metrics 与 /health/ready（P2-5）。

注：`prometheus_client` 是可选依赖；未安装时 /metrics 应返回 503，让运维知道关闭。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_metrics_endpoint_returns_text(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    pytest.importorskip("prometheus_client")
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        # 制造一次业务请求以增加计数
        client.get("/health")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "kb_qa_health_requests_total" in body
        # Prometheus exposition format 行
        assert "# HELP" in body and "# TYPE" in body


def test_health_ready_returns_503_when_no_providers(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    """active provider unavailable 且没有备选 → readiness 返回 503。"""
    fake_provider._configured = False
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert "active_provider" in body["checks"]
        assert body["checks"]["active_provider"]["ok"] is False


def test_health_ready_ok_when_provider_configured(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    fake_provider._configured = True
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["active_provider"]["ok"] is True
