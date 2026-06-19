"""api/security.py — API 鉴权依赖。

行为：
  - 未设置 KB_QA_API_TOKEN：dev / 本地默认放行（保持开发体验）
  - 设置 KB_QA_API_TOKEN：所有受保护端点要求 ``Authorization: Bearer <token>``
  - 校验失败 → 401 + ``WWW-Authenticate: Bearer``，不泄露 token

仅用于业务端点（``/v1/*``）；探活端点（``/health``、``/metrics``）保持公开。
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, status


def _expected_token() -> str:
    return (os.environ.get("KB_QA_API_TOKEN") or "").strip()


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency。鉴权失败抛 401。"""
    expected = _expected_token()
    if not expected:
        return

    auth = (authorization or "").strip()
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
            headers={"WWW-Authenticate": 'Bearer realm="kb-qa-agent"'},
        )
    presented = auth[len("bearer "):].strip()
    if presented != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token.",
            headers={"WWW-Authenticate": 'Bearer realm="kb-qa-agent"'},
        )


__all__ = ["require_api_token"]
