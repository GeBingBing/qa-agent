"""observability/logging_setup.py — 结构化日志 + request_id ContextVar。

  - 全局唯一 ``request_id_var`` ContextVar，便于 logger / tracer / cost 串联
  - JSON 行格式化器，``KB_QA_LOG_JSON=1`` 时启用；否则保留人类可读格式
  - 由 ``main.py`` 在启动时调用 ``install_logging()``，幂等
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import time

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "kb_qa_agent_request_id", default=""
)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_INSTALLED = False


def install_logging(level: str | None = None) -> None:
    """安装结构化日志 + request_id filter。幂等。"""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    log_level = (level or os.environ.get("KB_QA_LOG_LEVEL") or "INFO").upper()
    use_json = os.environ.get("KB_QA_LOG_JSON", "").strip() in {"1", "true", "yes"}

    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(request_id)s] %(name)s :: %(message)s",
        ))

    root = logging.getLogger()
    # 移除 basicConfig 装的默认 handler，避免重复打印
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(log_level)


__all__ = ["request_id_var", "install_logging", "JsonFormatter"]
