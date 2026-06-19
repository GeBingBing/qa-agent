"""observability/tracer.py — 简易 span 跟踪。

每个 span: {name, start, duration_ms, attrs, parent}
写日志到 .traces/<date>.jsonl；后续可接 OpenTelemetry。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..config import get_config
from .redact import redact, redact_attrs


@dataclass
class Span:
    span_id: str
    name: str
    parent_id: str | None
    start_ms: int
    end_ms: int
    duration_ms: int
    attrs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


_lock = threading.Lock()
_active_spans: dict[str, Span] = {}


def _trace_dir() -> Path:
    cfg = get_config()
    d = cfg.get("observability", {}).get("trace", {}).get("dir", "./.traces")
    Path(d).mkdir(parents=True, exist_ok=True)
    return Path(d)


def _write_span(span: Span) -> None:
    fname = _trace_dir() / f"{time.strftime('%Y-%m-%d')}.jsonl"
    payload = asdict(span)
    payload["attrs"] = redact_attrs(payload.get("attrs") or {})
    if payload.get("error"):
        payload["error"] = redact(payload["error"])
    with _lock:
        with fname.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


@contextmanager
def span(name: str, *, parent: str | None = None, attrs: dict[str, Any] | None = None):
    """上下文管理器形式的 span。"""
    sid = uuid.uuid4().hex[:12]
    start = time.time()
    s = Span(
        span_id=sid,
        name=name,
        parent_id=parent,
        start_ms=int(start * 1000),
        end_ms=0,
        duration_ms=0,
        attrs=attrs or {},
    )
    _active_spans[sid] = s
    try:
        yield s
    except Exception as exc:
        s.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        end = time.time()
        s.end_ms = int(end * 1000)
        s.duration_ms = s.end_ms - s.start_ms
        _active_spans.pop(sid, None)
        _write_span(s)


def current_span_id() -> str | None:
    """返回最近打开的 span id（用于嵌套时把子 span 关联起来）。"""
    return next(iter(reversed(_active_spans)), None)


__all__ = ["span", "current_span_id", "Span"]
