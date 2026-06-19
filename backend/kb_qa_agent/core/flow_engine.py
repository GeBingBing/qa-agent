"""flow_engine.py — TriggerFlow 包装（动态编译流 + 子流契约）。

封装 TriggerFlow 的常用模式：
  - build_flow(name) -> TriggerFlow
  - chunk 装饰器
  - sub-flow 契约：to_sub_flow(capture={input_key: data_input_field}, write_back={state_key: result})
  - 把 sub-flow 输出通过 data.input["result"] 喂给下游 chunk

业务层只需关心"我有哪些 chunk / 怎么连"，不需要接触 TriggerFlow 内部 API。
"""

from __future__ import annotations

from typing import Any

from agently import Agently

TriggerFlow = Any  # type: ignore
RuntimeData = Any  # type: ignore


def build_flow(name: str | None = None, *, skip_exceptions: bool = False) -> TriggerFlow:
    """工厂：建一个 TriggerFlow。"""
    return Agently.create_trigger_flow(name=name, skip_exceptions=skip_exceptions)


def chunk(*args: Any, **kwargs: Any):
    """TriggerFlow.chunk 的薄封装，方便未来切换。"""
    flow = kwargs.pop("_flow", None) or build_flow()
    return flow.chunk(*args, **kwargs)


def to_sub_flow(
    flow: TriggerFlow,
    subflow: TriggerFlow,
    *,
    capture: dict[str, str] | None = None,
    write_back: dict[str, str] | None = None,
):
    """把 subflow 接入当前 flow 的一个 chunk。

    capture:   {subflow_input_key: parent_data_input_field}    把父 data.input[xxx] 映射成 subflow 的 input[yyy]
    write_back:{parent_data_state_key: subflow_output_field}   subflow 完成后把 output 写回父 data.state[xxx]

    子流契约：subflow 内部必须通过 `await data.async_set_state("result", payload)` 暴露结果。
    """
    return flow.to_sub_flow(
        subflow,
        capture=capture,
        write_back=write_back,
    )


# ---------------------------------------------------------------------------
# 常用子流：单 LLM 调用（无状态）
# ---------------------------------------------------------------------------


def build_llm_chunk(flow: TriggerFlow, name: str, system: str, user_field: str = "input") -> Any:
    """一个最常用的 chunk：从 data.input[user_field] 取用户输入，调一次 LLM，把结果写入 data.state["result"]。"""
    from ..providers import ChatMessage  # local import 避免循环
    from .model_request import TaskExecutor

    @flow.chunk
    async def _llm_call(data: RuntimeData):
        user_input = data.input.get(user_field, "") if isinstance(data.input, dict) else str(data.input)
        msgs = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=str(user_input)),
        ]
        result = TaskExecutor().run_text(msgs, temperature=0.3)
        await data.async_set_state("result", result)
        return result

    _llm_call.__name__ = name
    return _llm_call


__all__ = ["build_flow", "chunk", "to_sub_flow", "build_llm_chunk", "TriggerFlow", "RuntimeData"]
