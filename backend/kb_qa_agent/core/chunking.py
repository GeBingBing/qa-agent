"""core/chunking.py — Markdown-aware 切分。

设计：
  - 解析 YAML frontmatter（可选）：返回 (metadata_dict, body_without_frontmatter)
  - 按 H1 / H2 / H3 切节；每个 chunk 维护 heading_path（祖先标题列表）
  - 节内按空行段落贪婪打包到 max_chars；相邻短段（< min_chars）合并
  - 代码块（``` 围栏）/ 表格 / 列表 整体保持，不在内部切断
  - 超长段落退化为字符 sliding window，仍保留所属 heading_path
  - 返回 list[ChunkPiece]，每条带 text、heading_path、char_len
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml  # type: ignore

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"^```")


@dataclass
class ChunkPiece:
    text: str
    heading_path: list[str] = field(default_factory=list)
    char_len: int = 0

    def __post_init__(self) -> None:
        if not self.char_len:
            self.char_len = len(self.text)


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """解析 YAML frontmatter；缺失时返回 ({}, raw)。"""
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    body = raw[m.end():]
    return meta, body


# ---------------------------------------------------------------------------
# 切分主流程
# ---------------------------------------------------------------------------


def chunk_markdown(
    raw: str,
    *,
    max_chars: int = 600,
    min_chars: int = 100,
    overlap_chars: int = 80,
    has_frontmatter: bool = True,
) -> list[ChunkPiece]:
    """把一份 markdown 文档切成若干 ChunkPiece。"""
    body = parse_frontmatter(raw)[1] if has_frontmatter else raw
    sections = _split_into_sections(body)
    pieces: list[ChunkPiece] = []
    for heading_path, section_text in sections:
        section_text = section_text.strip()
        if not section_text:
            continue
        for sub in _pack_section(section_text, max_chars=max_chars, min_chars=min_chars,
                                 overlap_chars=overlap_chars):
            pieces.append(ChunkPiece(text=sub, heading_path=list(heading_path)))
    return pieces


# ---------------------------------------------------------------------------
# 节切分
# ---------------------------------------------------------------------------


def _split_into_sections(body: str) -> list[tuple[list[str], str]]:
    """按 H1/H2/H3 切节，返回 [(heading_path, section_body)]。

    heading_path 是从根到当前节的祖先标题列表。
    """
    lines = body.split("\n")
    in_code = False
    sections: list[tuple[list[str], list[str]]] = []
    stack: list[tuple[int, str]] = []        # (level, title)
    current_lines: list[str] = []

    def flush():
        if current_lines and any(line.strip() for line in current_lines):
            path = [t for _, t in stack]
            sections.append((path, list(current_lines)))

    for line in lines:
        if _CODE_FENCE_RE.match(line):
            in_code = not in_code
            current_lines.append(line)
            continue
        m = _HEADING_RE.match(line) if not in_code else None
        if m:
            flush()
            current_lines = []
            level = len(m.group(1))
            title = m.group(2)
            # 弹出栈中 ≥ 当前级的标题
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            continue
        current_lines.append(line)
    flush()

    # 没有任何标题 → 整个 body 算一节，heading_path = []
    if not sections:
        return [([], body)]
    return [(path, "\n".join(lines)) for path, lines in sections]


# ---------------------------------------------------------------------------
# 节内打包
# ---------------------------------------------------------------------------


def _pack_section(
    text: str,
    *,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
) -> list[str]:
    """把一节文本切成 ≤ max_chars 的若干段。

    - 按空行段落 + 代码块边界做基本单元
    - 贪婪打包：累加 ≤ max_chars 时合并下一段
    - 相邻 < min_chars 的小段会被合并（受 max_chars 约束）
    - 单个段落超 max_chars：退化为 sliding window
    """
    units = _split_into_units(text)
    out: list[str] = []
    buf = ""
    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        if len(unit) > max_chars:
            # 先把当前 buffer 落地
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_sliding_window(unit, max_chars=max_chars, overlap_chars=overlap_chars))
            continue
        # 尝试把 unit 加进 buf
        candidate = (buf + "\n\n" + unit) if buf else unit
        if len(candidate) <= max_chars:
            buf = candidate
            continue
        # 装不下：buffer 落地，开新 buf
        if buf:
            out.append(buf)
        buf = unit
    if buf:
        out.append(buf)

    # 后处理：把太短的相邻 chunk 合并
    return _merge_short(out, min_chars=min_chars, max_chars=max_chars)


def _split_into_units(text: str) -> list[str]:
    """把节文本切成段落 / 代码块 / 表格组成的基本单元。"""
    lines = text.split("\n")
    units: list[list[str]] = []
    current: list[str] = []
    in_code = False

    def flush():
        if current:
            units.append(list(current))
            current.clear()

    for line in lines:
        if _CODE_FENCE_RE.match(line):
            if not in_code:
                # 进入 code block：先把当前段落落地
                flush()
                current.append(line)
                in_code = True
            else:
                # 退出 code block：把整个 code block 作为一个单元
                current.append(line)
                flush()
                in_code = False
            continue
        if in_code:
            current.append(line)
            continue
        if line.strip() == "":
            flush()
            continue
        current.append(line)
    flush()

    return ["\n".join(u) for u in units]


def _sliding_window(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    """字符级 sliding window；只用于超长单元的兜底。"""
    if len(text) <= max_chars:
        return [text]
    step = max(1, max_chars - overlap_chars)
    out: list[str] = []
    for i in range(0, len(text), step):
        chunk = text[i : i + max_chars]
        if not chunk.strip():
            continue
        out.append(chunk)
        if i + max_chars >= len(text):
            break
    return out


def _merge_short(chunks: list[str], *, min_chars: int, max_chars: int) -> list[str]:
    """把 < min_chars 的小 chunk 合并到相邻 chunk（不超过 max_chars）。"""
    if not chunks:
        return chunks
    out: list[str] = []
    for chunk in chunks:
        if not out:
            out.append(chunk)
            continue
        if len(out[-1]) < min_chars and len(out[-1]) + len(chunk) + 2 <= max_chars:
            out[-1] = out[-1] + "\n\n" + chunk
            continue
        if len(chunk) < min_chars and len(out[-1]) + len(chunk) + 2 <= max_chars:
            out[-1] = out[-1] + "\n\n" + chunk
            continue
        out.append(chunk)
    return out


__all__ = ["ChunkPiece", "chunk_markdown", "parse_frontmatter"]
