"""domains/_common.py — 各 domain 工具共用的 mock 数据加载器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MOCK_DIR = (Path(__file__).resolve().parents[3] / "data" / "mock_db").resolve()
_CACHE: dict[str, Any] = {}


def load_mock(domain: str) -> dict[str, Any]:
    """加载某 domain 的 mock JSON 数据（带缓存）。"""
    if domain in _CACHE:
        return _CACHE[domain]
    path = _MOCK_DIR / f"{domain}.json"
    if not path.exists():
        _CACHE[domain] = {}
        return _CACHE[domain]
    _CACHE[domain] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[domain]


def reload_mocks() -> None:
    """测试钩子：清缓存，强制重读 JSON。"""
    _CACHE.clear()
