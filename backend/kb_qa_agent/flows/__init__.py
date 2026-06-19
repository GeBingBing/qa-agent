"""flows/ — 5 个 sub-flow 构成端到端业务流水线。

流水线：
  intake → plan_gen → dep_executor → risk_approval → reflection

每个 sub-flow 都暴露一个 `run(...) -> dict` 同步入口 + `arun(...)` 异步入口，
便于业务层（api/chat.py / eval/run_eval.py）直接调用而不必关心 TriggerFlow 细节。
"""

from .dep_executor import aexecute_plan, execute_plan
from .intake import classify_intent
from .plan_gen import generate_plan
from .reflection import finalize_with_reflection
from .risk_approval import assess_and_route_risk

__all__ = [
    "classify_intent",
    "generate_plan",
    "execute_plan",
    "aexecute_plan",
    "assess_and_route_risk",
    "finalize_with_reflection",
]
