"""测试 observability/otel.py — OTel exporter 可选启用。

覆盖：
  - OTEL_EXPORTER_OTLP_ENDPOINT 未设置 → 不启用
  - 设置了 endpoint 但 SDK 缺失 → 降级 + warning
  - SDK + endpoint 都齐 → 注册 TracerProvider + BatchSpanProcessor
  - OTEL_SERVICE_NAME 缺失 → 默认 kb-qa-agent
  - 第二次调用幂等：已装则直接返回 True
  - is_installed / _reset_for_tests 状态翻转
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from kb_qa_agent.observability import otel as otel_mod


@pytest.fixture(autouse=True)
def _reset_otel_state():
    otel_mod._reset_for_tests()
    yield
    otel_mod._reset_for_tests()


def test_disabled_when_endpoint_not_set(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert otel_mod.install_otel_if_enabled() is False
    assert otel_mod.is_installed() is False


def test_disabled_when_endpoint_empty_string(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    assert otel_mod.install_otel_if_enabled() is False


def test_disabled_when_endpoint_whitespace_only(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "   ")
    assert otel_mod.install_otel_if_enabled() is False


def test_falls_back_when_sdk_missing(monkeypatch, caplog):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    # 让 _load_sdk() 返回 None
    monkeypatch.setattr(otel_mod, "_load_sdk", lambda: None)

    with caplog.at_level(logging.WARNING, logger="kb_qa_agent.observability.otel"):
        out = otel_mod.install_otel_if_enabled()

    assert out is False
    assert otel_mod.is_installed() is False
    assert any("opentelemetry SDK" in r.message or "OTLP exporter" in r.message for r in caplog.records)


def test_installs_when_sdk_available(monkeypatch):
    """SDK + exporter + endpoint 都齐 → 装好 TracerProvider + BatchSpanProcessor。"""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-svc")

    # 构造 fake SDK
    fake_provider = MagicMock(name="TracerProvider")
    fake_exporter = MagicMock(name="OTLPSpanExporter")
    fake_bsp = MagicMock(name="BatchSpanProcessor")

    sdk = SimpleNamespace(
        TracerProvider=MagicMock(return_value=fake_provider),
        BatchSpanProcessor=MagicMock(return_value=fake_bsp),
        OTLPSpanExporter=MagicMock(return_value=fake_exporter),
        Resource=SimpleNamespace(create=lambda attrs: attrs),
        set_global_provider=MagicMock(),
    )
    monkeypatch.setattr(otel_mod, "_load_sdk", lambda: sdk)

    out = otel_mod.install_otel_if_enabled()
    assert out is True
    assert otel_mod.is_installed() is True

    sdk.TracerProvider.assert_called_once()
    sdk.OTLPSpanExporter.assert_called_once_with(endpoint="http://localhost:4318")
    fake_provider.add_span_processor.assert_called_once()
    sdk.set_global_provider.assert_called_once_with(fake_provider)


def test_default_service_name_when_env_missing(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    captured_attrs: list[dict] = []

    def fake_create(attrs):
        captured_attrs.append(attrs)
        return attrs

    sdk = SimpleNamespace(
        TracerProvider=MagicMock(),
        BatchSpanProcessor=MagicMock(),
        OTLPSpanExporter=MagicMock(),
        Resource=SimpleNamespace(create=fake_create),
        set_global_provider=MagicMock(),
    )
    monkeypatch.setattr(otel_mod, "_load_sdk", lambda: sdk)

    otel_mod.install_otel_if_enabled()
    assert captured_attrs == [{"service.name": "kb-qa-agent"}]


def test_idempotent_second_call_returns_true_without_reinstall(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    sdk = SimpleNamespace(
        TracerProvider=MagicMock(),
        BatchSpanProcessor=MagicMock(),
        OTLPSpanExporter=MagicMock(),
        Resource=SimpleNamespace(create=lambda attrs: attrs),
        set_global_provider=MagicMock(),
    )
    monkeypatch.setattr(otel_mod, "_load_sdk", lambda: sdk)

    assert otel_mod.install_otel_if_enabled() is True
    assert otel_mod.install_otel_if_enabled() is True
    # TracerProvider 只被构造一次
    assert sdk.TracerProvider.call_count == 1
    assert otel_mod.is_installed() is True


def test_load_sdk_returns_simple_namespace_on_success(monkeypatch):
    """_load_sdk 正常路径：返回带 TracerProvider/.../set_global_provider 的 SimpleNamespace。"""
    # 不 mock，让真实 import 走；如果失败就 skip
    sdk = otel_mod._load_sdk()
    if sdk is None:
        pytest.skip("opentelemetry sdk not installed in test env")
    assert hasattr(sdk, "TracerProvider")
    assert hasattr(sdk, "BatchSpanProcessor")
    assert hasattr(sdk, "OTLPSpanExporter")
    assert hasattr(sdk, "Resource")
    assert hasattr(sdk, "set_global_provider")
