"""测试 P2-6：可选 OTel exporter。

设计契约：
  - install_otel_if_enabled() 在 OTEL_EXPORTER_OTLP_ENDPOINT 未设置时直接返回，不报错
  - 设置了但 SDK / exporter 缺失：返回 False 并 logger.warning，不抛
  - 设置了且 SDK 齐：注册 TracerProvider + BatchSpanProcessor + OTLPSpanExporter，返回 True
  - install 是幂等的：重复调用不会重复注册
"""

from __future__ import annotations

import logging


def test_install_returns_false_when_endpoint_unset(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from kb_qa_agent.observability import otel as otel_mod

    otel_mod._reset_for_tests()
    assert otel_mod.install_otel_if_enabled() is False
    assert otel_mod.is_installed() is False


def test_install_returns_false_when_sdk_missing(monkeypatch, caplog):
    """SDK 不可用时不应抛，应 warning 后降级。"""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    from kb_qa_agent.observability import otel as otel_mod

    otel_mod._reset_for_tests()
    monkeypatch.setattr(otel_mod, "_load_sdk", lambda: None)
    with caplog.at_level(logging.WARNING):
        ok = otel_mod.install_otel_if_enabled()
    assert ok is False
    assert otel_mod.is_installed() is False
    assert any("opentelemetry" in r.message.lower() for r in caplog.records)


def test_install_succeeds_with_fake_sdk(monkeypatch):
    """SDK 齐时应注册 provider + processor + exporter。"""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "kb-qa-agent-test")

    from kb_qa_agent.observability import otel as otel_mod

    otel_mod._reset_for_tests()

    captured: dict = {}

    class FakeProvider:
        def __init__(self, resource):
            captured["resource"] = resource
            self.processors = []

        def add_span_processor(self, p):
            self.processors.append(p)

    class FakeBatchProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeExporter:
        def __init__(self, **kw):
            captured["exporter_kwargs"] = kw

    class FakeResource:
        @staticmethod
        def create(attrs):
            captured["resource_attrs"] = attrs
            return ("res", attrs)

    fake_sdk = type("S", (), {
        "TracerProvider": FakeProvider,
        "BatchSpanProcessor": FakeBatchProcessor,
        "OTLPSpanExporter": FakeExporter,
        "Resource": FakeResource,
        "set_global_provider": lambda p: captured.update({"global": p}),
    })

    monkeypatch.setattr(otel_mod, "_load_sdk", lambda: fake_sdk)
    assert otel_mod.install_otel_if_enabled() is True
    assert otel_mod.is_installed() is True
    assert captured["resource_attrs"]["service.name"] == "kb-qa-agent-test"
    assert captured["exporter_kwargs"]["endpoint"] == "http://localhost:4318"
    assert isinstance(captured["global"], FakeProvider)
    assert len(captured["global"].processors) == 1


def test_install_is_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    from kb_qa_agent.observability import otel as otel_mod

    otel_mod._reset_for_tests()
    calls = {"n": 0}

    class FakeProvider:
        def __init__(self, resource):
            calls["n"] += 1

        def add_span_processor(self, p):
            pass

    fake_sdk = type("S", (), {
        "TracerProvider": FakeProvider,
        "BatchSpanProcessor": lambda exp: None,
        "OTLPSpanExporter": lambda **kw: None,
        "Resource": type("R", (), {"create": staticmethod(lambda a: a)}),
        "set_global_provider": lambda p: None,
    })

    monkeypatch.setattr(otel_mod, "_load_sdk", lambda: fake_sdk)
    assert otel_mod.install_otel_if_enabled() is True
    assert otel_mod.install_otel_if_enabled() is True   # 幂等：仍 True，但只创建一次
    assert calls["n"] == 1
