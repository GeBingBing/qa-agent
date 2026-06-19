"""core/ — 核心引擎模块。

每个文件提供一类能力：

  model_request.py   单次请求 + schema 输出 + TaskExecutor
  flow_engine.py     多步流程编排 + TriggerFlow 子流契约
  tool_registry.py   ToolRegistry（按 domain / side_effect 分类）
  react_loop.py      Reason→Act ReAct 循环 + Grace Call 预算降级
  router.py          意图路由（4 域 + general）
  planner.py         DAG 规划 + Kahn 拓扑排序校验
  reflection.py      Draft → Evaluate → Revise 反思循环
  rag.py             ChromaDB RAG 封装
  sandbox.py         bash 沙盒（命令白名单 + 超时）
  skill_loader.py    Skills 加载 / 选择 / 信任门
"""

from .flow_engine import build_flow, build_llm_chunk, chunk, to_sub_flow
from .model_request import TaskExecutor, quick_structured, quick_text
from .planner import (
    Plan,
    PlanNode,
    PlannerError,
    plan_dag,
    plan_with_retry,
    topological_order,
    validate_plan,
)
from .react_loop import REACT_SCHEMA, ReActLoop, ReActResult, ReActStep
from .reflection import (
    DEFAULT_REPORT_CRITERIA,
    EVAL_SCHEMA,
    EvaluationResult,
    evaluate_draft,
    reflect_and_revise,
    revise_draft,
)
from .router import ROUTER_SCHEMA, DomainName, route_query
from .rag import RAG, RetrievalHit, chunk_text
from .sandbox import BashSandbox, SandboxError, SandboxResult
from .skill_loader import (
    SELECT_SCHEMA,
    DecisionCard,
    TrustDecision,
    apply_trust_gate,
    load_decision_cards,
    select_by_model,
    select_required,
)
from .tool_registry import GLOBAL_REGISTRY, ToolRegistry, ToolSpec

__all__ = [
    # model_request
    "TaskExecutor", "quick_text", "quick_structured",
    # flow_engine
    "build_flow", "build_llm_chunk", "chunk", "to_sub_flow",
    # tool_registry
    "ToolRegistry", "ToolSpec", "GLOBAL_REGISTRY",
    # react_loop
    "ReActLoop", "ReActStep", "ReActResult", "REACT_SCHEMA",
    # router
    "route_query", "ROUTER_SCHEMA", "DomainName",
    # planner
    "Plan", "PlanNode", "PlannerError", "plan_dag", "plan_with_retry", "validate_plan", "topological_order",
    # reflection
    "EvaluationResult", "evaluate_draft", "revise_draft", "reflect_and_revise",
    "DEFAULT_REPORT_CRITERIA", "EVAL_SCHEMA",
    # rag
    "RAG", "RetrievalHit", "chunk_text",
    # sandbox
    "BashSandbox", "SandboxResult", "SandboxError",
    # skill_loader
    "DecisionCard", "load_decision_cards", "select_by_model", "select_required",
    "apply_trust_gate", "TrustDecision", "SELECT_SCHEMA",
]
