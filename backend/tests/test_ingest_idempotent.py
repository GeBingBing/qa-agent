"""测试 P4-A2：RAG 摄取幂等性。

期望：
  - 相同 source 二次写入，先删旧再写新 → 数据库总量不变
  - chunk id 与 source + sha1(text) 关联，而不是位置
  - metadata 含 heading_path / doc_hash / ingested_at / embedding_model
  - 内容变更（同 source 不同文本）→ 旧 chunk 全部清理
"""

from __future__ import annotations

import pytest


class FakeCollection:
    """记录对 ChromaDB collection 的所有调用。"""

    def __init__(self):
        self.docs: dict[str, dict] = {}     # id → {text, metadata}

    def add(self, *, ids, documents, metadatas):
        for i, t, m in zip(ids, documents, metadatas, strict=True):
            self.docs[i] = {"text": t, "metadata": dict(m)}

    def delete(self, *, where=None):
        if not where:
            self.docs.clear()
            return
        # 简化：仅支持单 key 等值匹配
        keep = {}
        for i, doc in self.docs.items():
            ok = all(doc["metadata"].get(k) == v for k, v in where.items())
            if not ok:
                keep[i] = doc
        self.docs = keep

    def query(self, **kw):
        # 此处不需要真查询
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture
def fake_rag(monkeypatch, tmp_path):
    from kb_qa_agent.core.rag import RAG

    rag = RAG()
    rag._persist_dir = str(tmp_path)
    rag._client = object()       # 标志已 init
    rag._collection_obj = FakeCollection()
    rag._embed_fn = object()
    return rag


def test_same_doc_re_ingest_does_not_grow(fake_rag):
    docs = [
        ("# H1\n\nHello world", {"source": "policy.md", "domain": "hr"}),
    ]
    n1 = fake_rag.add_documents(docs)
    snapshot1 = dict(fake_rag._collection_obj.docs)
    n2 = fake_rag.add_documents(docs)
    snapshot2 = dict(fake_rag._collection_obj.docs)

    # 第二次 add 应当先删旧再写：总量恒定
    assert n1 > 0
    assert n2 == n1
    assert len(snapshot2) == len(snapshot1)
    # 由于 id 是 source+sha1，重复写应得到同一组 id
    assert set(snapshot1.keys()) == set(snapshot2.keys())


def test_changed_content_replaces_old_chunks(fake_rag):
    fake_rag.add_documents([("# H1\n\nVersion A.", {"source": "p.md", "domain": "hr"})])
    ids_a = set(fake_rag._collection_obj.docs.keys())
    fake_rag.add_documents([("# H1\n\nCompletely different version B with more content.",
                            {"source": "p.md", "domain": "hr"})])
    ids_b = set(fake_rag._collection_obj.docs.keys())
    # 新内容应当替换旧 chunk；不应有 A 残留
    for cid in ids_a:
        assert cid not in ids_b or fake_rag._collection_obj.docs[cid]["text"] != "Version A."


def test_metadata_includes_heading_path_and_doc_hash(fake_rag):
    fake_rag.add_documents([
        (
            "# Doc title\n\n"
            "## Section A\n\n" + ("段落 A 内容。" * 30) + "\n\n"
            "## Section B\n\n" + ("段落 B 内容。" * 30),
            {"source": "p.md", "domain": "hr"},
        ),
    ])
    metas = [d["metadata"] for d in fake_rag._collection_obj.docs.values()]
    assert all("heading_path" in m for m in metas)
    assert all("doc_hash" in m for m in metas)
    assert all("ingested_at" in m for m in metas)
    paths = [m["heading_path"] for m in metas]
    assert any("Section A" in p for p in paths)
    assert any("Section B" in p for p in paths)


def test_different_sources_coexist(fake_rag):
    fake_rag.add_documents([("# A\n\nA body", {"source": "a.md", "domain": "hr"})])
    fake_rag.add_documents([("# B\n\nB body", {"source": "b.md", "domain": "hr"})])
    sources = {d["metadata"]["source"] for d in fake_rag._collection_obj.docs.values()}
    assert sources == {"a.md", "b.md"}


def test_embedding_model_recorded(fake_rag):
    fake_rag._embedding_model = "BAAI/bge-small-zh-v1.5"
    fake_rag._embedding_provider = "local"
    fake_rag.add_documents([("# X\n\nText", {"source": "x.md"})])
    metas = [d["metadata"] for d in fake_rag._collection_obj.docs.values()]
    assert all(m.get("embedding_model") == "BAAI/bge-small-zh-v1.5" for m in metas)
    assert all(m.get("embedding_provider") == "local" for m in metas)
