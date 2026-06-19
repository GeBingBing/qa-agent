"""测试 PII redact（P2-4）。

期望：
  - <think>...</think> 块被剥离
  - sk-* / Bearer token 被屏蔽
  - 长 query 被截断到 50 字符
  - 嵌套结构（dict / list）也会逐层 redact
"""

from __future__ import annotations

from kb_qa_agent.observability.redact import redact, redact_attrs


def test_redact_strips_thinking_block():
    raw = "<think>这是私密推理</think>真正的输出"
    assert redact(raw) == "真正的输出"


def test_redact_masks_sk_tokens():
    raw = "调用 OpenAI: sk-abc123XYZ_TOKEN_VERY_LONG_VALUE-001"
    out = redact(raw)
    assert "sk-abc123XYZ_TOKEN_VERY_LONG_VALUE-001" not in out
    assert "[redacted]" in out


def test_redact_masks_bearer_token():
    raw = "Authorization: Bearer s3cr3t-token-please-hide"
    out = redact(raw)
    assert "s3cr3t-token-please-hide" not in out
    assert "Bearer [redacted]" in out


def test_redact_truncates_long_string():
    raw = "x" * 200
    out = redact(raw, max_len=50)
    assert len(out) <= 50 + len("…(truncated)")
    assert out.endswith("…(truncated)")


def test_redact_attrs_handles_nested_structures():
    attrs = {
        "query": "用户问 sk-abcdefghijklmnopqrst000000",
        "history": [
            {"role": "user", "content": "<think>secret</think>hi"},
            {"role": "assistant", "content": "Bearer real-token-here-please"},
        ],
        "count": 3,
        "ratio": 0.42,
    }
    out = redact_attrs(attrs)
    assert "sk-abcdefghijklmnopqrst000000" not in out["query"]
    assert "<think>" not in out["history"][0]["content"]
    assert "real-token-here-please" not in out["history"][1]["content"]
    assert out["count"] == 3
    assert out["ratio"] == 0.42


def test_tracer_writes_redacted_attrs(tmp_path, monkeypatch):
    """tracer.span 写入磁盘的 attrs / error 必须经过 redact。"""
    import json
    monkeypatch.setenv("KB_QA_TRACE_DIR", str(tmp_path))

    from kb_qa_agent.observability import tracer as tracer_mod
    monkeypatch.setattr(tracer_mod, "_trace_dir", lambda: tmp_path)

    try:
        with tracer_mod.span("test", attrs={
            "query": "<think>thought</think>用户问 sk-1234567890ABCDEFGH",
            "auth": "Bearer real-token-please-hide",
        }):
            raise RuntimeError("boom: sk-9876543210ZYXWVUTSRQ")
    except RuntimeError:
        pass

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(line)
    assert "<think>" not in payload["attrs"]["query"]
    assert "sk-1234567890ABCDEFGH" not in payload["attrs"]["query"]
    assert "real-token-please-hide" not in payload["attrs"]["auth"]
    # 错误信息中的 sk- 也要被屏蔽
    assert "sk-9876543210ZYXWVUTSRQ" not in payload["error"]
