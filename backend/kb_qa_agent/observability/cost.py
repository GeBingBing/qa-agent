"""observability/cost.py — 成本累计器。

每次 LLM 调用后用 ChatResponse.usage × provider.price_per_1k() 计算 USD 成本，
累加到会话级 cost 记录。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import get_config
from ..providers import get_provider


@dataclass
class CostEntry:
    ts: float
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class CostReport:
    entries: list[CostEntry] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return round(sum(e.cost_usd for e in self.entries), 6)

    @property
    def total_input_tokens(self) -> int:
        return sum(e.input_tokens for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        return sum(e.output_tokens for e in self.entries)

    def to_dict(self) -> dict:
        return {
            "total_usd": self.total_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "by_provider": self._by_provider(),
            "entries": [asdict(e) for e in self.entries[-200:]],   # 最近 200 条
        }

    def _by_provider(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.entries:
            bucket = out.setdefault(e.provider, {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0})
            bucket["usd"] += e.cost_usd
            bucket["input_tokens"] += e.input_tokens
            bucket["output_tokens"] += e.output_tokens
            bucket["calls"] += 1
        for v in out.values():
            v["usd"] = round(v["usd"], 6)
        return out


_lock = threading.Lock()
_REPORT = CostReport()


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """按 provider × token 单价计算 USD。"""
    p = get_provider(provider)
    in_cost = (input_tokens / 1000.0) * p.price_per_1k(model, "input")
    out_cost = (output_tokens / 1000.0) * p.price_per_1k(model, "output")
    return round(in_cost + out_cost, 6)


def record(provider: str, model: str, usage: dict[str, int]) -> CostEntry:
    """把一次 LLM 调用记到全局报表。"""
    in_t = int(usage.get("prompt_tokens", 0))
    out_t = int(usage.get("completion_tokens", 0))
    entry = CostEntry(
        ts=time.time(),
        provider=provider,
        model=model,
        input_tokens=in_t,
        output_tokens=out_t,
        cost_usd=estimate_cost(provider, model, in_t, out_t),
    )
    with _lock:
        _REPORT.entries.append(entry)
    return entry


def get_report() -> CostReport:
    with _lock:
        return CostReport(entries=list(_REPORT.entries))


def reset_report() -> None:
    with _lock:
        _REPORT.entries.clear()


def save_report_to_disk(path: str | Path | None = None) -> Path:
    cfg = get_config()
    p = Path(path or cfg.get("observability", {}).get("cost", {}).get("report_path", "./.cost/report.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(get_report().to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


__all__ = ["CostEntry", "CostReport", "estimate_cost", "record", "get_report", "reset_report", "save_report_to_disk"]
