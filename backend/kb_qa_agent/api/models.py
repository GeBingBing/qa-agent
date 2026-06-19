"""api/models.py — Pydantic 数据模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /v1/chat 请求体。"""
    query: str = Field(..., description="用户原始问题")
    conversation_history: list[dict[str, Any]] = Field(default_factory=list, description="可选的多轮历史")
    provider: str | None = Field(None, description="覆盖 .env 的 active provider")
    model: str | None = Field(None, description="覆盖 provider 默认 model")
    enable_reflection: bool = Field(True, description="是否走反思迭代")
    enable_rag: bool = Field(True, description="是否启用 RAG 检索")
    enable_skills: bool = Field(True, description="是否启用 Skills 选择")


class StreamEvent(BaseModel):
    """SSE 推送给前端的单个事件。"""
    event: Literal[
        "start",            # 流开始
        "intake",           # classify_intent 结果
        "plan",             # DAG 生成结果
        "step_start",       # 节点开始执行
        "step_result",      # 节点执行结果
        "risk",             # 风险评估结果
        "reflection",       # 反思迭代进度
        "final",            # 最终回答
        "error",            # 错误
    ]
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = 0.0


class HealthResponse(BaseModel):
    status: str
    active_provider: str
    available_providers: list[str]
    total_tools: int
    skills_loaded: int
