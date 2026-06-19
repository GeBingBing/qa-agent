"""bootstrap_kb.py — 把 data/knowledge_base/{hr,finance,it,legal}/*.md 导入 ChromaDB。

用法：
    python -m eval.bootstrap_kb
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from kb_qa_agent.core import RAG  # noqa: E402

KB_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge_base"


def main() -> None:
    rag = RAG()
    count = 0
    if not KB_DIR.exists():
        print(f"KB dir not found: {KB_DIR}")
        print("Create sample policies in data/knowledge_base/{hr,finance,it,legal}/ first.")
        return
    for domain_dir in sorted(KB_DIR.iterdir()):
        if not domain_dir.is_dir():
            continue
        domain = domain_dir.name
        for md_file in sorted(domain_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            metadata = {"domain": domain, "source": md_file.name, "doc_id": md_file.stem}
            rag.add_documents([(text, metadata)])
            print(f"  indexed {md_file.relative_to(KB_DIR.parent.parent)} ({len(text)} chars)")
            count += 1
    print(f"Done. {count} documents indexed.")


if __name__ == "__main__":
    main()
