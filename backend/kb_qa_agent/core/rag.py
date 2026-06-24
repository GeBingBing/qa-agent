"""rag.py — ChromaDB RAG 封装。

设计：
  - 单 collection：kb_policies
  - embedding：本地 sentence-transformers (BAAI/bge-small-zh-v1.5)
    或 OpenAI text-embedding-3-small（可切）
  - 切分走 markdown-aware (`core/chunking.py`)，保留 heading_path
  - 摄取幂等：id = sha1(source + text)，重写前先按 source 删旧 chunk
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_config
from .chunking import chunk_markdown


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
        """docs: iterable of (raw_markdown_text, metadata)。

        语义：
          - 同 source 二次写入 → 先 delete(where={"source": ...}) 再 add，幂等
          - chunk id = sha1(source + chunk_text)[:16]，与位置无关
          - metadata 写入 heading_path / doc_hash / ingested_at /
            embedding_model / embedding_provider，便于审计与脏数据排查
          - 切分走 chunk_markdown（保留章节结构）；缺 frontmatter 也兼容
        """
        self._ensure_client()
        self._ensure_embed_fn()

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        sources_to_clear: set[str] = set()
        ingested_at = int(time.time())

        for text, metadata in docs:
            metadata = dict(metadata or {})
            source = str(metadata.get("source") or metadata.get("doc_id") or "")
            if source:
                sources_to_clear.add(source)
            doc_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
            pieces = chunk_markdown(text, max_chars=600, min_chars=100, overlap_chars=80)
            for j, piece in enumerate(pieces):
                cid_base = f"{source or 'inline'}::{doc_hash}::{j}::{piece.text}"
                cid = hashlib.sha1(cid_base.encode("utf-8")).hexdigest()[:16]
                ids.append(cid)
                texts.append(piece.text)
                m = dict(metadata)
                m.update({
                    "chunk_index": j,
                    "char_len": piece.char_len,
                    "heading_path": "/".join(piece.heading_path) if piece.heading_path else "",
                    "doc_hash": doc_hash,
                    "ingested_at": ingested_at,
                    "embedding_model": self._embedding_model,
                    "embedding_provider": self._embedding_provider,
                })
                metadatas.append(m)

        # 幂等：先按 source 清理旧 chunk
        for src in sources_to_clear:
            try:
                self._collection_obj.delete(where={"source": src})
            except Exception:  # noqa: BLE001 — 兼容某些 chroma 版本对 empty where 的差异
                pass

        if ids:
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
        for text, meta, dist in zip(docs, metas, dists, strict=False):
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
