"""测试 P0-6：ChatRequest 的 provider/model 请求级覆盖真实生效。

要求：
  - TaskExecutor() 默认读取 active_provider()
  - api/chat 路径用 with model_request.request_provider("opus"): 把 provider/model 透传到所有 sub-flow
  - 退出 context 后恢复成原 active provider
"""

from __future__ import annotations

from kb_qa_agent.core.model_request import TaskExecutor, request_provider


def test_task_executor_uses_request_provider_context(fake_provider, monkeypatch):
    """在 request_provider 上下文里 TaskExecutor 应使用指定 provider。"""
    from kb_qa_agent.providers import registry as registry_mod

    fake2 = type(fake_provider)()
    fake2.name = "fake2"
    fake2.chat_response_text = "from-fake2"
    monkeypatch.setitem(registry_mod.PROVIDER_REGISTRY, "fake2", fake2)

    with request_provider("fake2", model="m-2"):
        ex = TaskExecutor()
        assert ex.provider_name == "fake2"
        assert ex.model_name == "m-2"
        assert ex.run_text([{"role": "user", "content": "hi"}]) == "from-fake2"


def test_task_executor_falls_back_to_active_when_no_context(fake_provider):
    ex = TaskExecutor()
    assert ex.provider_name == "fake"
    assert ex.model_name is None


def test_request_provider_restores_previous_state(fake_provider, monkeypatch):
    from kb_qa_agent.providers import registry as registry_mod

    fake2 = type(fake_provider)()
    fake2.name = "fake2"
    monkeypatch.setitem(registry_mod.PROVIDER_REGISTRY, "fake2", fake2)

    with request_provider("fake2"):
        assert TaskExecutor().provider_name == "fake2"
    assert TaskExecutor().provider_name == "fake"


def test_request_provider_unknown_provider_raises(fake_provider):
    import pytest

    with pytest.raises(KeyError):
        with request_provider("does-not-exist"):
            pass
