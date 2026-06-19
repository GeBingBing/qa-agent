"""flows/risk_approval.py — 风险评估与人工审批路由。

输入 dep_executor 的 results；调模型判断整体风险等级：
  - low        → 自动放行
  - medium     → 提示但不阻断
  - high       → 阻断，要求人工审批（业务层 await user input / webhook）
"""

from __future__ import annotations

import json
from typing import Any

from ..core import TaskExecutor
from ..providers import ChatMessage


RISK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "risk_level": {"type": "string", "description": "low / medium / high"},
        "auto_proceed": {"type": "boolean", "description": "是否可以不经过人工审批直接生成最终回答"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "required_approver": {"type": "string", "description": "auto / manager / legal / cfo"},
    },
    "required": ["risk_level", "auto_proceed", "reasons", "required_approver"],
}


_RISK_SYSTEM = """你是企业知识库问答系统的风险评估员。

输入：用户问题 + 各步骤执行结果（tool observation + llm content + human placeholder）。
任务：判断整个回答是否存在需要人工介入的风险。

风险等级：
  - low:    常规政策咨询，无合规风险
  - medium: 涉及金额 / 权限变更 / 个人数据；建议复核但可自动推进
  - high:   涉及法律合规 / 大额资金 / 跨境数据 / 高敏感操作；必须人工审批

需要人工审批的场景举例：
  - 法务合规检查发现 risk=high 的结果
  - 报销金额超过 10000 元
  - 涉及跨境数据传输
  - 修改生产权限 / admin 权限

输出严格 JSON。"""


def assess_and_route_risk(user_query: str, execution_results: dict[str, Any]) -> dict[str, Any]:
    """评估风险并给出路由建议。"""
    summary = json.dumps(execution_results, ensure_ascii=False, indent=2, default=str)[:6000]
    user_prompt = (
        f"## 用户问题\n{user_query}\n\n"
        f"## 执行结果\n{summary}\n\n"
        "请输出风险评估 JSON。"
    )
    raw = TaskExecutor().run_structured(
        [ChatMessage(role="system", content=_RISK_SYSTEM), ChatMessage(role="user", content=user_prompt)],
        schema=RISK_SCHEMA,
        temperature=0.1,
    )
    # 强制 risk_level 合法
    rl = str(raw.get("risk_level", "low")).lower()
    if rl not in {"low", "medium", "high"}:
        rl = "low"
    raw["risk_level"] = rl
    return raw


__all__ = ["assess_and_route_risk", "RISK_SCHEMA"]
