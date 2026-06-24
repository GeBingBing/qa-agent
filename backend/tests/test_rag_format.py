"""测试 core/rag.py 中尚未覆盖的纯函数 / 边界。

覆盖：
  - chunk_text() 朴素字符切分（短 / 长 / overlap）
  - format_hits() 空 + 非空 + source / doc_id 字段回退
  - RAG._ensure_embed_fn() 未知 provider → NotImplementedError
  - RAG.add_documents() delete 抛异常时静默继续
  - RAG() 默认配置（persist dir / collection / embedding_model）
"""

from __future__ import annotations

import pytest
from kb_qa_agent.core.rag import RAG, RetrievalHit, chunk_text

# ---------------------------------------------------------------------------
# chunk_text — 朴素字符切分
# ---------------------------------------------------------------------------


def test_chunk_text_short_text_returned_as_single_chunk():
    """短文本（≤ chunk_size）原样返回。"""
    out = chunk_text("hello", chunk_size=100, overlap=10)
    assert out == ["hello"]


def test_chunk_text_overlap_split():
    """长文本按 chunk_size - overlap 步进切。"""
    text = "A" * 1000
    out = chunk_text(text, chunk_size=300, overlap=100)
    # 步进 = 200, 1000 长度 → 5 段 (i=0,200,400,600,800 → 取 [0:300],[200:500],[400:700],[600:900],[800:1000])
    assert len(out) == 5
    assert len(out[0]) == 300
    assert len(out[-1]) == 200  # 最后一段可能较短
    # overlap 检查：相邻 chunk 共享 100 字符
    assert out[0][200:300] == out[1][:100]


def test_chunk_text_strips_whitespace():
    """首尾空白先剥除。"""
    out = chunk_text("  abc  ", chunk_size=100)
    assert out == ["abc"]


def test_chunk_text_exact_boundary():
    """长度正好 == chunk_size → 仍按 1 段返回。"""
    out = chunk_text("X" * 100, chunk_size=100, overlap=10)
    assert out == ["X" * 100]


# ---------------------------------------------------------------------------
# format_hits
# ---------------------------------------------------------------------------


def test_format_hits_empty_returns_placeholder():
    rag = RAG()
    assert rag.format_hits([]) == "(no relevant documents found)"


def test_format_hits_uses_source_field():
    rag = RAG()
    hits = [
        RetrievalHit(text="alpha", metadata={"source": "policy.md", "domain": "hr"}, score=0.1),
        RetrievalHit(text="beta", metadata={"source": "policy2.md"}, score=0.5),
    ]
    out = rag.format_hits(hits)
    assert "[1] (source=policy.md" in out
    assert "alpha" in out
    assert "[2] (source=policy2.md" in out
    assert "---" in out  # 分隔符


def test_format_hits_falls_back_to_doc_id_when_source_missing():
    rag = RAG()
    hits = [RetrievalHit(text="x", metadata={"doc_id": "doc-1"}, score=0.2)]
    out = rag.format_hits(hits)
    assert "(source=doc-1" in out


def test_format_hits_falls_back_to_question_mark_when_both_missing():
    rag = RAG()
    hits = [RetrievalHit(text="x", metadata={}, score=0.2)]
    out = rag.format_hits(hits)
    assert "(source=?" in out


# ---------------------------------------------------------------------------
# RAG 默认配置
# ---------------------------------------------------------------------------


def test_rag_default_config_uses_local_bge_model():
    rag = RAG()
    assert rag._embedding_provider == "local"
    assert "bge" in rag._embedding_model.lower()
    assert rag._collection == "kb_policies"


# ---------------------------------------------------------------------------
# 未知 embedding provider → NotImplementedError
# ---------------------------------------------------------------------------


def test_ensure_embed_fn_unknown_provider_raises(monkeypatch):
    rag = RAG()
    rag._embedding_provider = "huggingface-api"  # 不在白名单内
    with pytest.raises(NotImplementedError, match="huggingface-api"):
        rag._ensure_embed_fn()


# ---------------------------------------------------------------------------
# delete 异常吞掉
# ---------------------------------------------------------------------------


class _ThrowOnDeleteCollection:
    """record add 调用；delete 抛异常 → 测试不应传播。"""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    def add(self, *, ids, documents, metadatas):
        for i, t, m in zip(ids, documents, metadatas, strict=True):
            self.docs[i] = {"text": t, "metadata": dict(m)}

    def delete(self, *, where=None):
        raise RuntimeError("chroma delete kaboom")

    def query(self, **kw):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def test_add_documents_tolerates_delete_exception(monkeypatch):
    """同 source 二次 add_documents 时 delete 抛异常不应冒泡。"""
    rag = RAG()
    rag._client = object()
    rag._collection_obj = _ThrowOnDeleteCollection()
    rag._embed_fn = object()
    # 不应抛
    n = rag.add_documents([("# X\n\nbody", {"source": "x.md"})])
    assert n > 0


# ---------------------------------------------------------------------------
# 多个 source → delete 都执行
# ---------------------------------------------------------------------------


class _RecordingDeleteCollection:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.delete_calls: list[dict] = []

    def add(self, *, ids, documents, metadatas):
        for i, t, m in zip(ids, documents, metadatas, strict=True):
            self.docs[i] = {"text": t, "metadata": dict(m)}

    def delete(self, *, where=None):
        self.delete_calls.append(dict(where or {}))
        if where:
            for cid, doc in list(self.docs.items()):
                if all(doc["metadata"].get(k) == v for k, v in where.items()):
                    del self.docs[cid]

    def query(self, **kw):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def test_add_documents_delete_called_per_source(monkeypatch):
    rag = RAG()
    rag._client = object()
    rag._collection_obj = _RecordingDeleteCollection()
    rag._embed_fn = object()
    rag.add_documents([
        ("# A\n\nA body", {"source": "a.md"}),
        ("# B\n\nB body", {"source": "b.md"}),
    ])
    # 两次 delete 调用，各对应一个 source
    assert len(rag._collection_obj.delete_calls) == 2
    assert {c.get("source") for c in rag._collection_obj.delete_calls} == {"a.md", "b.md"}
