"""测试 API Bearer 鉴权（P2-1）。

期望：
  - 未设置 KB_QA_API_TOKEN → 鉴权关闭（dev/本地体验不变）
  - 设置 KB_QA_API_TOKEN → /v1/chat 必须带 Bearer，否则 401
  - /health 与 /metrics 不要求鉴权（用于探活）
  - 错误的 token → 401，带 WWW-Authenticate
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from kb_qa_agent.api.security import require_api_token


def test_require_api_token_disabled_when_env_missing(monkeypatch):
    monkeypatch.delenv("KB_QA_API_TOKEN", raising=False)
    # 不带 token 也应该放行
    require_api_token(authorization=None)


def test_require_api_token_accepts_matching_bearer(monkeypatch):
    monkeypatch.setenv("KB_QA_API_TOKEN", "secret-xyz")
    require_api_token(authorization="Bearer secret-xyz")


def test_require_api_token_rejects_missing(monkeypatch):
    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("KB_QA_API_TOKEN", "secret-xyz")
    with pytest.raises(HTTPException) as exc:
        require_api_token(authorization=None)
    assert exc.value.status_code == 401


def test_require_api_token_rejects_wrong(monkeypatch):
    import pytest
    from fastapi import HTTPException

    monkeypatch.setenv("KB_QA_API_TOKEN", "secret-xyz")
    with pytest.raises(HTTPException) as exc:
        require_api_token(authorization="Bearer wrong")
    assert exc.value.status_code == 401


def test_chat_endpoint_requires_bearer_when_token_set(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    monkeypatch.setenv("KB_QA_API_TOKEN", "secret-xyz")
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        # 未带 token
        resp = client.post("/v1/chat", json={"query": "hi"})
        assert resp.status_code == 401
        # 错 token
        resp = client.post("/v1/chat", json={"query": "hi"}, headers={"Authorization": "Bearer bad"})
        assert resp.status_code == 401


def test_health_endpoint_does_not_require_auth(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    monkeypatch.setenv("KB_QA_API_TOKEN", "secret-xyz")
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
