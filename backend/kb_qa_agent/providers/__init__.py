"""providers/ — 7 家 LLM Provider 适配层。

公开 API：
    from kb_qa_agent.providers import get_provider, list_available, active_provider, PROVIDER_REGISTRY
    from kb_qa_agent.providers import BaseProvider, ChatMessage, ChatResponse, StreamChunk

业务层用 `get_provider(name)` 拿到统一接口的 Provider 实例；
或用 `active_provider()` 让 .env 的 KB_QA_ACTIVE_PROVIDER 起作用。

注册顺序：deepseek / openai / opus / kimi / glm / dashscope / minimax。
详见 docs/PROVIDER_SETUP.md。

启动顺序说明：.registry.PROVIDER_REGISTRY 在模块 import 时 eager 构造，构造期间
OpenAICompatProvider.__init__ 会读 os.environ 拿 API key。因此我们必须在 import
registry **之前** 先 load_dotenv()，否则 registry 会拿到空 api_key，list_available() 返回空。
"""

from pathlib import Path

from dotenv import load_dotenv

# 在 import 子模块（尤其是 .registry）之前先把 .env 加载到 os.environ。
# 路径层级：__file__ = backend/kb_qa_agent/providers/__init__.py
# parents[0]=providers, parents[1]=kb_qa_agent, parents[2]=backend, parents[3]=repo_root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
for _cand in (_PROJECT_ROOT / ".env", Path.cwd() / ".env"):
    if _cand.exists():
        load_dotenv(_cand, override=False)
        break

from . import env_keys  # noqa: E402
from .agently_adapter import configure_agently_for_active_provider  # noqa: E402
from .base import (  # noqa: E402
    BaseProvider,
    ChatMessage,
    ChatResponse,
    StreamChunk,
)
from .claude import ClaudeProvider  # noqa: E402
from .openai_compat import OpenAICompatProvider  # noqa: E402
from .registry import (  # noqa: E402
    PROVIDER_REGISTRY,
    active_provider,
    get_provider,
    list_all,
    list_available,
)
from .structured import build_structured_messages, parse_json_response  # noqa: E402

__all__ = [
    # core types
    "BaseProvider",
    "ChatMessage",
    "ChatResponse",
    "StreamChunk",
    # concrete impls
    "OpenAICompatProvider",
    "ClaudeProvider",
    # registry
    "PROVIDER_REGISTRY",
    "get_provider",
    "list_available",
    "list_all",
    "active_provider",
    # structured helpers
    "build_structured_messages",
    "parse_json_response",
    # agently bridge
    "configure_agently_for_active_provider",
    "env_keys",
]
