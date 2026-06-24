"""测试 core/chunking.py — markdown-aware 切分。

期望：
  - frontmatter 不进入 chunk 文本
  - 按 H1/H2/H3 切节，每个 chunk 携带 heading_path
  - 节内按段落贪婪打包到 max_chars，相邻短段合并
  - code fence / 表格 不被切断
  - 超长段落退化为 sliding window，仍保留 heading 上下文
  - 返回 dataclass / dict 含 text、heading_path、char_len 字段
"""

from __future__ import annotations

from kb_qa_agent.core.chunking import ChunkPiece, chunk_markdown, parse_frontmatter


def test_parse_frontmatter_returns_metadata_and_body():
    raw = """---
title: Hello
domain: hr
keywords:
  - a
  - b
---

# H1

Body text.
"""
    fm, body = parse_frontmatter(raw)
    assert fm["title"] == "Hello"
    assert fm["domain"] == "hr"
    assert fm["keywords"] == ["a", "b"]
    assert body.lstrip().startswith("# H1")


def test_parse_frontmatter_when_absent_returns_empty():
    raw = "# Hello\n\nNo frontmatter here.\n"
    fm, body = parse_frontmatter(raw)
    assert fm == {}
    assert body == raw


def test_chunk_markdown_splits_by_h2():
    text = """# Doc

## Section A

Para A1.

## Section B

Para B1.
"""
    pieces = chunk_markdown(text, max_chars=200, min_chars=10)
    _titles = [p.heading_path for p in pieces]  # noqa: F841 — 本地调试用
    # Doc / Section A / Section B 的 heading_path 至少能分辨
    paths = ["/".join(p.heading_path) for p in pieces]
    assert any("Section A" in p for p in paths)
    assert any("Section B" in p for p in paths)
    for p in pieces:
        assert p.char_len == len(p.text)
        assert p.char_len > 0


def test_chunk_markdown_keeps_code_fence_intact():
    text = """## API

```python
def f():
    pass
```

End.
"""
    pieces = chunk_markdown(text, max_chars=100, min_chars=10)
    full = "\n".join(p.text for p in pieces)
    assert "```python" in full
    assert "def f():" in full
    # 任何单个 chunk 不应只含半截 code fence
    for p in pieces:
        opens = p.text.count("```")
        assert opens % 2 == 0, f"code fence broken: {p.text!r}"


def test_chunk_markdown_long_paragraph_falls_back_to_sliding_window():
    long_para = "段落" * 600
    text = f"## Long Section\n\n{long_para}\n"
    pieces = chunk_markdown(text, max_chars=400, min_chars=50, overlap_chars=80)
    assert len(pieces) >= 2
    # 每个 chunk 都保留 heading_path
    for p in pieces:
        assert "Long Section" in p.heading_path
        assert p.char_len <= 500   # 略宽容（含 overlap）


def test_chunk_markdown_merges_short_neighbours():
    text = """## Tiny

A.

B.

C.
"""
    pieces = chunk_markdown(text, max_chars=200, min_chars=20)
    # 短段落应该被合并到一起，而不是产生 3 个一行的 chunk
    assert len(pieces) == 1


def test_chunk_piece_is_dataclass_like():
    """ChunkPiece 至少应该有 text/heading_path/char_len 三个属性。"""
    p = ChunkPiece(text="hi", heading_path=["A"], char_len=2)
    assert p.text == "hi"
    assert p.heading_path == ["A"]
    assert p.char_len == 2
