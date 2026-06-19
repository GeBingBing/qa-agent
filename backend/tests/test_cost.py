"""测试 cost 累计器（P2-7）。

期望：
  - estimate_cost 按 provider 定价计算
  - record / get_report 线性累加
  - reset_report 清空
  - save_report_to_disk 写出 JSON
"""

from __future__ import annotations

from kb_qa_agent.observability.cost import (
    estimate_cost,
    get_report,
    record,
    reset_report,
    save_report_to_disk,
)


def test_estimate_cost_uses_provider_price(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com")
    cost = estimate_cost("openai", "gpt-4o", 1000, 500)
    expected = (1000 / 1000) * 0.00015 + (500 / 1000) * 0.00060
    assert cost == round(expected, 6)


def test_record_and_get_report():
    reset_report()
    record("openai", "gpt-4o", {"prompt_tokens": 100, "completion_tokens": 50})
    record("openai", "gpt-4o", {"prompt_tokens": 200, "completion_tokens": 100})
    report = get_report()
    assert len(report.entries) == 2
    assert report.total_input_tokens == 300
    assert report.total_output_tokens == 150
    assert report.total_usd > 0


def test_reset_report_clears():
    reset_report()
    record("openai", "gpt-4o", {"prompt_tokens": 10, "completion_tokens": 5})
    assert len(get_report().entries) == 1
    reset_report()
    assert len(get_report().entries) == 0


def test_save_report_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com")
    reset_report()
    record("openai", "gpt-4o", {"prompt_tokens": 100, "completion_tokens": 50})
    p = save_report_to_disk(tmp_path / ".cost" / "report.json")
    assert p.exists()
    import json
    data = json.loads(p.read_text())
    assert data["total_usd"] > 0
    assert len(data["entries"]) == 1