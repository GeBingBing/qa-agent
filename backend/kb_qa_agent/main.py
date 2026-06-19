"""kb_qa_agent.main — FastAPI 应用入口。

启动：
    uvicorn kb_qa_agent.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import chat as chat_api
from .api import health as health_api
from .config import get_config, reset_config_cache
from .domains import bootstrap as bootstrap_domains
from .observability.logging_setup import install_logging
from .observability.request_id_middleware import RequestIdMiddleware
from .providers import configure_agently_for_active_provider, list_available


install_logging()
logger = logging.getLogger("kb_qa_agent")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时：加载 .env + 配置 Agently + 注册 4 域工具。"""
    # 加载 .env
    from pathlib import Path
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for c in candidates:
        if c.exists():
            load_dotenv(c, override=False)
            logger.info("loaded .env from %s", c)
            break
    reset_config_cache()
    cfg = get_config()
    cors_origins = cfg.get("api", {}).get("cors_origins", "http://localhost:5173")
    if isinstance(cors_origins, str):
        cors_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

    # 注入 Agently
    agently_summary = configure_agently_for_active_provider()
    logger.info("Agently configured: %s", agently_summary)

    # 注册 4 域工具
    bootstrap_domains()
    logger.info("domain tools registered; available providers: %s", list_available())

    # 共享 RAG 单例（embedding 模型加载昂贵，避免每请求重建）
    from .core.rag import RAG
    _app.state.rag = RAG()

    yield


app = FastAPI(
    title="kb-qa-agent",
    version="0.1.0",
    description="企业知识库问答助手 — 多 Provider LLM + RAG + MCP + Skills + 沙盒 + 反思",
    lifespan=lifespan,
)

# CORS
def build_cors_kwargs(cors_origins: str | list[str] | None) -> dict[str, object]:
    """根据配置生成 CORSMiddleware 的 kwargs。

    - 显式 origins 列表 → 保留 allow_credentials=True
    - 通配 ``"*"`` → 强制 allow_credentials=False（浏览器规范禁止两者并存）
    - 空 / None → fallback 到 ["http://localhost:5173"]，不再静默退到 ["*"]
    """
    if isinstance(cors_origins, str):
        origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    elif isinstance(cors_origins, list):
        origins = [o.strip() for o in cors_origins if o and o.strip()]
    else:
        origins = []

    if not origins:
        origins = ["http://localhost:5173"]

    allow_credentials = origins != ["*"]
    return {
        "allow_origins": origins,
        "allow_credentials": allow_credentials,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


cfg = get_config()
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    **build_cors_kwargs(cfg.get("api", {}).get("cors_origins", "http://localhost:5173")),
)

# 路由
app.include_router(health_api.router)
app.include_router(chat_api.router)


@app.get("/")
async def root():
    return {
        "name": "kb-qa-agent",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "chat": "POST /v1/chat (SSE)",
    }
