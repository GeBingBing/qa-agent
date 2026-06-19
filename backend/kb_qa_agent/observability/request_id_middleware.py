"""middleware: 注入 / 回显 request_id 到 ContextVar + 响应头。"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging_setup import request_id_var

HEADER_NAME = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """把客户端的 ``X-Request-Id`` 写入 ContextVar；缺失时生成新 UUID。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(HEADER_NAME) or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[HEADER_NAME] = rid
        return response


__all__ = ["RequestIdMiddleware", "HEADER_NAME"]
