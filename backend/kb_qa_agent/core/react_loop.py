"""react_loop.py — ReAct 循环（Reason→Act→Observe pattern）。

兼容两种运行模式：
  - Simple mode（同步、单步）：reason() 返回 dict，act() 调一次 tool，把结果写回 history
  - Loop mode（带 step budget）：最多 N 步；Grace Call 当预算耗尽时强切 final

输出接口：
  - 返回 dict 含 final_answer / steps / total_usage
  - 支持 async iterator（async for chunk in run_stream()）便于 SSE 流式推送
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ..providers import ChatMessage
from .model_request import TaskExecutor
from .tool_registry import GLOBAL_REGISTRY, ToolRegistry

REACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "description": "'tool' or 'final'"},
        "reasoning": {"type": "string"},
        "tool_name": {"type": "string"},
        "tool_args": {"type": "object"},
        "answer": {"type": "string"},
    },
    "required": ["type", "reasoning"],
}


REACT_SYSTEM = """你是一个 ReAct 推理代理。

每一步你需要输出一个 JSON 对象：
  - type='tool'：表示你要调用一个工具
    必须填写 tool_name (从可用工具列表里选) 和 tool_args (dict)
  - type='final'：表示你已经准备好给出最终答案
    必须填写 answer

可用工具会在用户消息中以"## 可用工具"段列出。
规则：
  1. 每次只输出一个 JSON 对象，不要解释
  2. 最多调用 max_steps 次工具；如果工具调用耗尽预算，请直接 type='final' 并基于已有信息给出答案
  3. 工具结果会以"## 工具结果"段回灌给你
  4. 最终答案要求简洁、准确、可执行
"""


@dataclass
class ReActStep:
    step: int
    decision: dict[str, Any]
    observation: Any = None
    duration_ms: int = 0
    error: str | None = None


@dataclass
class ReActResult:
    final_answer: str
    steps: list[ReActStep] = field(default_factory=list)
    total_usage: dict[str, int] = field(default_factory=dict)
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_answer": self.final_answer,
            "steps": [
                {
                    "step": s.step,
                    "decision": s.decision,
                    "observation": s.observation,
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "total_usage": self.total_usage,
            "provider": self.provider,
            "model": self.model,
        }


class ReActLoop:
    """ReAct 循环执行器。"""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        max_steps: int = 6,
        tool_ids: list[str] | None = None,
        executor: TaskExecutor | None = None,
    ):
        self.registry = registry or GLOBAL_REGISTRY
        self.max_steps = max_steps
        self.tool_ids = tool_ids  # None = registry 全部
        self.executor = executor or TaskExecutor()

    def _available_tools_prompt(self) -> str:
        specs = (
            [self.registry.get(i) for i in self.tool_ids]
            if self.tool_ids
            else self.registry.list()
        )
        if not specs:
            return "（无可用工具）"
        return self.registry.to_prompt_blocks([s.id for s in specs])

    def _build_step_messages(
        self,
        user_query: str,
        history: list[dict[str, Any]],
        budget_left: int,
    ) -> list[ChatMessage]:
        extra_instruct = ""
        if budget_left <= 1:
            extra_instruct = f"\n\n⚠️ 步骤预算只剩 {budget_left} 步，请直接 type='final' 并基于现有信息给出最佳回答。"

        tools_block = self._available_tools_prompt()
        history_text = self._format_history(history)
        user = (
            f"## 原始问题\n{user_query}\n\n"
            f"## 可用工具\n{tools_block}\n\n"
            f"## 当前步骤历史\n{history_text or '(刚开始)'}{extra_instruct}\n\n"
            "请输出下一步决策（严格 JSON）。"
        )
        return [
            ChatMessage(role="system", content=REACT_SYSTEM + extra_instruct),
            ChatMessage(role="user", content=user),
        ]

    @staticmethod
    def _format_history(history: list[dict[str, Any]]) -> str:
        if not history:
            return ""
        blocks = []
        for i, h in enumerate(history, 1):
            decision = h.get("decision", {})
            observation = h.get("observation")
            blocks.append(
                f"### Step {i}\n"
                f"decision: {json.dumps(decision, ensure_ascii=False)}\n"
                f"observation: {json.dumps(observation, ensure_ascii=False) if observation is not None else 'None'}"
            )
        return "\n\n".join(blocks)

    async def run(self, user_query: str, *, initial_context: dict[str, Any] | None = None) -> ReActResult:
        history: list[dict[str, Any]] = []
        total_usage: dict[str, int] = {}
        final_answer = ""
        budget_left = self.max_steps

        for step_idx in range(self.max_steps):
            budget_left = self.max_steps - step_idx
            t0 = time.perf_counter()
            try:
                decision = self.executor.run_structured(
                    self._build_step_messages(user_query, history, budget_left),
                    schema=REACT_SCHEMA,
                    temperature=0.2,
                )
            except Exception as exc:
                decision = {"type": "final", "reasoning": f"structured parse failed: {exc}", "answer": self._fallback_answer(user_query, history)}

            decision_type = str(decision.get("type", "")).lower()

            if decision_type == "final":
                final_answer = decision.get("answer") or self._fallback_answer(user_query, history)
                history.append({"decision": decision, "observation": None})
                return ReActResult(
                    final_answer=final_answer,
                    steps=[ReActStep(step=step_idx + 1, decision=decision, duration_ms=int((time.perf_counter() - t0) * 1000))],
                    total_usage=total_usage,
                    provider=self.executor.provider_name,
                )

            if decision_type == "tool":
                tool_name = decision.get("tool_name", "")
                tool_args = decision.get("tool_args", {}) or {}
                try:
                    observation = await self.registry.execute(tool_name, **tool_args)
                except Exception as exc:
                    observation = {"error": str(exc)}
                history.append({"decision": decision, "observation": observation})
                duration = int((time.perf_counter() - t0) * 1000)
                # 记录本步
                if not hasattr(self, "_steps_buf"):
                    object.__setattr__(self, "_steps_buf", [])
                buf = getattr(self, "_steps_buf", [])
                buf.append(ReActStep(step=step_idx + 1, decision=decision, observation=observation, duration_ms=duration))
                continue

            # unknown type — 强切 final
            final_answer = f"(unknown decision type: {decision_type!r}) {decision.get('reasoning', '')}"
            return ReActResult(
                final_answer=final_answer,
                steps=[ReActStep(step=step_idx + 1, decision=decision, duration_ms=int((time.perf_counter() - t0) * 1000))],
                total_usage=total_usage,
                provider=self.executor.provider_name,
            )

        # 预算耗尽 — Grace Call
        grace_decision = self.executor.run_structured(
            self._build_step_messages(user_query, history, budget_left=0),
            schema=REACT_SCHEMA,
            temperature=0.2,
        )
        if str(grace_decision.get("type", "")).lower() == "final":
            final_answer = grace_decision.get("answer", "")
        else:
            final_answer = self._fallback_answer(user_query, history)
        return ReActResult(
            final_answer=final_answer,
            steps=getattr(self, "_steps_buf", []),
            total_usage=total_usage,
            provider=self.executor.provider_name,
        )

    async def run_stream(self, user_query: str, *, initial_context: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
        """异步流式输出。每步 / 每 observation 都 push 一个事件。

        Events:
          {"event": "step_start", "step": int}
          {"event": "decision", "step": int, "decision": dict}
          {"event": "observation", "step": int, "observation": any}
          {"event": "final", "final_answer": str, "total_usage": dict}
        """
        history: list[dict[str, Any]] = []
        final_answer = ""
        total_usage: dict[str, int] = {}

        for step_idx in range(self.max_steps):
            budget_left = self.max_steps - step_idx
            yield {"event": "step_start", "step": step_idx + 1, "budget_left": budget_left}
            try:
                decision = self.executor.run_structured(
                    self._build_step_messages(user_query, history, budget_left),
                    schema=REACT_SCHEMA,
                    temperature=0.2,
                )
            except Exception as exc:
                decision = {"type": "final", "reasoning": f"structured parse failed: {exc}", "answer": self._fallback_answer(user_query, history)}
            yield {"event": "decision", "step": step_idx + 1, "decision": decision}

            decision_type = str(decision.get("type", "")).lower()
            if decision_type == "final":
                final_answer = decision.get("answer") or self._fallback_answer(user_query, history)
                yield {"event": "final", "final_answer": final_answer, "total_usage": total_usage}
                return

            if decision_type == "tool":
                tool_name = decision.get("tool_name", "")
                tool_args = decision.get("tool_args", {}) or {}
                try:
                    observation = await self.registry.execute(tool_name, **tool_args)
                except Exception as exc:
                    observation = {"error": str(exc)}
                history.append({"decision": decision, "observation": observation})
                yield {"event": "observation", "step": step_idx + 1, "observation": observation}
                continue

            # unknown
            final_answer = f"(unknown decision type: {decision_type!r}) {decision.get('reasoning', '')}"
            yield {"event": "final", "final_answer": final_answer, "total_usage": total_usage}
            return

        # Grace Call
        grace = self.executor.run_structured(
            self._build_step_messages(user_query, history, budget_left=0),
            schema=REACT_SCHEMA,
            temperature=0.2,
        )
        if str(grace.get("type", "")).lower() == "final":
            final_answer = grace.get("answer", "")
        else:
            final_answer = self._fallback_answer(user_query, history)
        yield {"event": "final", "final_answer": final_answer, "total_usage": total_usage}

    @staticmethod
    def _fallback_answer(user_query: str, history: list[dict[str, Any]]) -> str:
        if not history:
            return f"抱歉，关于「{user_query}」我暂时没有足够信息回答。请提供更多上下文或换个问法。"
        obs_summary = []
        for h in history[-3:]:
            o = h.get("observation")
            if isinstance(o, dict) and "error" in o:
                obs_summary.append(f"工具调用失败：{o['error']}")
            elif o is not None:
                obs_summary.append(str(o)[:200])
        return "根据已收集的信息（" + "；".join(obs_summary) + "），暂时无法给出完整答案，建议联系对应负责人。"


__all__ = ["ReActLoop", "ReActStep", "ReActResult", "REACT_SCHEMA"]
