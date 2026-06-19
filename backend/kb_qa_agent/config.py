"""config.py — 应用配置加载。

约定：
  - .env 提供密钥 / base_url / 端口
  - SETTINGS.yaml 提供可调业务参数（domain 列表、skill trust 等级）
  - ${ENV.*} 占位符在 .env 缺失时回退到空串（运行时由 Provider 层判断 available）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

# 项目根 = 本文件向上 2 级 = ~/Documents/work_agent/kb-qa-agent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = Path(__file__).resolve().parent / "SETTINGS.yaml"


def _load_dotenv() -> None:
    """加载 .env（项目根目录优先，找不到也不报错）。"""
    candidates = [
        PROJECT_ROOT / ".env",
        BACKEND_ROOT / ".env",
        Path.cwd() / ".env",
    ]
    for c in candidates:
        if c.exists():
            load_dotenv(c, override=False)
            return
    # 兜底：find_dotenv 会向上搜；找不到时静默
    load_dotenv(find_dotenv(usecwd=True), override=False)


def _substitute_env(data: Any) -> Any:
    """递归把 "${ENV.NAME}" 占位符替换为 os.environ[name]。"""
    if isinstance(data, dict):
        return {k: _substitute_env(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_substitute_env(v) for v in data]
    if isinstance(data, str):
        if data.startswith("${ENV.") and data.endswith("}"):
            key = data[len("${ENV.") : -1]
            return os.environ.get(key, "")
        return data
    return data


def load_settings() -> dict[str, Any]:
    """加载并解析 SETTINGS.yaml。"""
    _load_dotenv()
    if not SETTINGS_PATH.exists():
        return {}
    import yaml  # type: ignore
    raw = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8"))
    return _substitute_env(raw) or {}


# 单例配置（懒加载）
_CONFIG_CACHE: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    """全局配置缓存。修改 .env 后需重启进程。"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = load_settings()
    return _CONFIG_CACHE


def reset_config_cache() -> None:
    """测试钩子：强制重读 .env + YAML。"""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
