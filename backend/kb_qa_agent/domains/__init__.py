"""domains/ — 4 个业务域的 mock 工具。

调用 `kb_qa_agent.domains.bootstrap()` 把所有 12 个工具注册到 GLOBAL_REGISTRY。
bootstrap() 是幂等的，可重复调用。
"""

from . import finance, hr, it, legal
from ..core.tool_registry import GLOBAL_REGISTRY


_BOOTSTRAPPED = False


def bootstrap() -> None:
    """注册 4 个域的全部工具到 GLOBAL_REGISTRY。幂等。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    hr.register()
    finance.register()
    it.register()
    legal.register()
    _BOOTSTRAPPED = True


def reset_bootstrap_flag() -> None:
    """测试钩子：清掉 bootstrap 标志，让下一次 bootstrap() 重新注册。"""
    global _BOOTSTRAPPED
    _BOOTSTRAPPED = False


__all__ = ["bootstrap", "reset_bootstrap_flag", "hr", "finance", "it", "legal", "GLOBAL_REGISTRY"]
