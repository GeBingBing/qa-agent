"""observability/redact.py — 写入磁盘前的 PII / secret 屏蔽。

策略：
  - 剥离 ``<think>...</think>`` 块（避免私密推理写入磁盘）
  - 屏蔽 ``sk-`` 风格 API key
  - 屏蔽 ``Authorization: Bearer ...`` token
  - 单字段最大 1024 字符（query / message 默认截到该长度）
  - 字典 / 列表 / 嵌套结构按值类型递归处理；非字符串原样保留

用于 trace span attrs / cost 报告 / log extra。
"""

from __future__ import annotations

import re
from typing import Any

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_SK_TOKEN_RE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}")

DEFAULT_MAX_LEN = 1024


def redact(value: str, *, max_len: int = DEFAULT_MAX_LEN) -> str:
    """对单个字符串做剥离 + 屏蔽 + 截断。"""
    if not isinstance(value, str):
        return value
    cleaned = _THINK_RE.sub("", value)
    cleaned = _SK_TOKEN_RE.sub("[redacted]", cleaned)
    cleaned = _BEARER_RE.sub("Bearer [redacted]", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "…(truncated)"
    return cleaned


def redact_attrs(attrs: Any, *, max_len: int = DEFAULT_MAX_LEN) -> Any:
    """递归 redact dict / list / str；其他类型原样返回。"""
    if isinstance(attrs, dict):
        return {k: redact_attrs(v, max_len=max_len) for k, v in attrs.items()}
    if isinstance(attrs, list):
        return [redact_attrs(item, max_len=max_len) for item in attrs]
    if isinstance(attrs, tuple):
        return tuple(redact_attrs(item, max_len=max_len) for item in attrs)
    if isinstance(attrs, str):
        return redact(attrs, max_len=max_len)
    return attrs


__all__ = ["redact", "redact_attrs", "DEFAULT_MAX_LEN"]
