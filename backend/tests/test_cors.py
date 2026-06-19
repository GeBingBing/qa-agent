"""测试 CORS 配置。

P2-2 期望：
  - 显式 origins 列表 + allow_credentials=True，按预期工作
  - cors_origins 配成 "*" + credentials 时禁用 credentials（避免 RFC 6454 + Cookie 双标 risk）
  - cors_origins 为空时 fallback 不再是 ["*"]，而是项目默认 ["http://localhost:5173"]
"""

from __future__ import annotations

from kb_qa_agent.main import build_cors_kwargs


def test_explicit_origins_list_keeps_credentials():
    kwargs = build_cors_kwargs("http://localhost:5173,https://example.com")
    assert kwargs["allow_origins"] == ["http://localhost:5173", "https://example.com"]
    assert kwargs["allow_credentials"] is True


def test_wildcard_origin_disables_credentials():
    kwargs = build_cors_kwargs("*")
    assert kwargs["allow_origins"] == ["*"]
    # 浏览器规范：Access-Control-Allow-Origin: * 与 Access-Control-Allow-Credentials: true 不能同时存在
    assert kwargs["allow_credentials"] is False


def test_empty_origins_falls_back_to_local_dev():
    kwargs = build_cors_kwargs("")
    assert kwargs["allow_origins"] == ["http://localhost:5173"]
    assert kwargs["allow_credentials"] is True


def test_list_origins_preserved():
    kwargs = build_cors_kwargs(["http://a", "http://b"])
    assert kwargs["allow_origins"] == ["http://a", "http://b"]
    assert kwargs["allow_credentials"] is True


def test_origins_strip_whitespace_and_drop_blanks():
    kwargs = build_cors_kwargs("  http://a , , http://b ")
    assert kwargs["allow_origins"] == ["http://a", "http://b"]
