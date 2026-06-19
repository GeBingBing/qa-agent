"""测试 request_id 中间件 + 结构化日志（P2-3）。

期望：
  - 客户端没传 X-Request-Id：服务端生成 UUID 并回写到响应头
  - 客户端传了 X-Request-Id：原样回显（便于跨服务串联），ContextVar 可读
  - chat handler 内 request_id_var.get() 能拿到当前请求 id
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_request_id_generated_when_missing(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        rid = resp.headers.get("x-request-id")
        assert rid and len(rid) >= 8


def test_request_id_echoed_when_provided(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    from kb_qa_agent.main import app

    with TestClient(app) as client:
        resp = client.get("/health", headers={"X-Request-Id": "trace-test-001"})
        assert resp.headers.get("x-request-id") == "trace-test-001"


def test_request_id_var_visible_in_handler(monkeypatch, fake_provider, reset_registry, reset_bootstrap):
    from kb_qa_agent.main import app
    from kb_qa_agent.observability.logging_setup import request_id_var

    captured: list[str] = []

    @app.get("/_test/echo-rid")
    async def echo_rid():  # type: ignore[reportUnusedFunction]
        captured.append(request_id_var.get())
        return {"rid": request_id_var.get()}

    with TestClient(app) as client:
        resp = client.get("/_test/echo-rid", headers={"X-Request-Id": "fixed-rid-42"})
        assert resp.json() == {"rid": "fixed-rid-42"}
        assert captured == ["fixed-rid-42"]
