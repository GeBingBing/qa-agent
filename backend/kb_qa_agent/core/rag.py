"""rag.py — ChromaDB RAG 封装。

设计：
  - 单 collection：kb_policies
  - embedding：本地 sentence-transformers (BAAI/bge-small-zh-v1.5)
    或 OpenAI text-embedding-3-small（可切）
  - chunk_size / overlap 简单按字符切；生产可换 markdown-aware splitter
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..config import get_config


@dataclass
class RetrievalHit:
    text: str
    metadata: dict[str, Any]
    score: float          # distance: 越小越相关


class RAG:
    """ChromaDB 包装。懒加载，避免启动时强制要求 chromadb 安装。"""

    def __init__(self):
        cfg = get_config()
        rag_cfg = cfg.get("rag", {}) or {}
        self._persist_dir = rag_cfg.get("chroma", {}).get("persist_dir", "./data/chroma")
        self._collection = rag_cfg.get("chroma", {}).get("collection", "kb_policies")
        self._embedding_provider = rag_cfg.get("embedding", {}).get("provider", "local")
        self._embedding_model = rag_cfg.get("embedding", {}).get("model", "BAAI/bge-small-zh-v1.5")
        self._client = None
        self._collection_obj = None
        self._embed_fn = None

    # ---------- lazy init ----------
    def _ensure_client(self):
        if self._client is not None:
            return
        import chromadb  # type: ignore
        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection_obj = self._client.get_or_create_collection(
            name=self._collection,
            metadata={"hnsw:space": "cosine"},
        )

    def _ensure_embed_fn(self):
        if self._embed_fn is not None:
            return
        cache_folder = (
            os.environ.get("KB_QA_HF_HOME")
            or os.environ.get("HF_HOME")
            or os.environ.get("SENTENCE_TRANSFORMERS_HOME")
        )
        if self._embedding_provider == "local":
            from chromadb.utils import embedding_functions  # type: ignore
            kwargs: dict[str, Any] = {"model_name": self._embedding_model}
            if cache_folder:
                kwargs["cache_folder"] = cache_folder
            self._embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(**kwargs)
        elif self._embedding_provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            from chromadb.utils import embedding_functions  # type: ignore
            self._embed_fn = embedding_functions.OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small",
            )
        else:
            raise NotImplementedError(f"Embedding provider {self._embedding_provider!r} not implemented")

    # ---------- ingest ----------
    def add_documents(self, docs: Iterable[tuple[str, dict[str, Any]]]) -> int:
        """docs: iterable of (text, metadata). 自动切分 + 写入 collection."""
        self._ensure_client()
        self._ensure_embed_fn()

        ids, texts, metadatas = [], [], []
        for idx, (text, metadata) in enumerate(docs):
            chunks = chunk_text(text, chunk_size=500, overlap=80)
            for j, chunk in enumerate(chunks):
                ids.append(f"doc-{idx}-{j}")
                texts.append(chunk)
                m = dict(metadata or {})
                m["chunk_index"] = j
                m["char_len"] = len(chunk)
                metadatas.append(m)
        self._collection_obj.add(ids=ids, documents=texts, metadatas=metadatas)
        return len(ids)

    # ---------- query ----------
    def retrieve(self, query: str, *, top_k: int = 5, where: dict[str, Any] | None = None) -> list[RetrievalHit]:
        self._ensure_client()
        kwargs: dict[str, Any] = {"query_texts": [query], "n_results": top_k}
        if where:
            kwargs["where"] = where
        res = self._collection_obj.query(**kwargs)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out: list[RetrievalHit] = []
        for text, meta, dist in zip(docs, metas, dists):
            out.append(RetrievalHit(text=text, metadata=meta or {}, score=float(dist)))
        return out

    def format_hits(self, hits: list[RetrievalHit]) -> str:
        if not hits:
            return "(no relevant documents found)"
        blocks = []
        for i, h in enumerate(hits, 1):
            src = h.metadata.get("source", h.metadata.get("doc_id", "?"))
            blocks.append(f"[{i}] (source={src}, score={h.score:.3f})\n{h.text}")
        return "\n\n---\n\n".join(blocks)


def chunk_text(text: str, *, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    """朴素字符切分；生产可换 markdown / sentence-aware。"""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    step = chunk_size - overlap
    for i in range(0, len(text), step):
        chunks.append(text[i : i + chunk_size])
        if i + chunk_size >= len(text):
            break
    return chunks


__all__ = ["RAG", "RetrievalHit", "chunk_text"]
