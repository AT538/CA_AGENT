"""
Build the local embedding index from syllabus.json + pyqs.json.

Run this once, and again only when you update the syllabus or add new PYQs.
The resulting index is committed to the repo (knowledge_base/index/) so
daily runs never need to rebuild it.
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent
INDEX_DIR = BASE_DIR / "index"
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[warn] {path} not found, skipping")
        return []
    return json.loads(path.read_text())


def main():
    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=str(INDEX_DIR))

    # Fresh collection each build - simplest way to avoid stale entries
    client.delete_collection("upsc_knowledge") if "upsc_knowledge" in [
        c.name for c in client.list_collections()
    ] else None
    collection = client.create_collection("upsc_knowledge")

    docs, ids, metadatas = [], [], []

    for topic in load_json(BASE_DIR / "syllabus.json"):
        text = f"{topic['topic']}: {topic['description']}"
        docs.append(text)
        ids.append(f"syllabus-{topic['id']}")
        metadatas.append({
            "type": "syllabus",
            "paper": topic["paper"],
            "topic": topic["topic"],
        })

    for i, q in enumerate(load_json(BASE_DIR / "pyqs.json")):
        docs.append(q["question"])
        ids.append(f"pyq-{q.get('paper', 'unknown')}-{q['year']}-{i}")
        metadatas.append({
            "type": "pyq",
            "year": q["year"],
            "paper": q.get("paper", "unknown"),  # prelims_gs1 | mains_gs1..4
            "topics": ",".join(q.get("topics", [])),
        })

    if not docs:
        print("Nothing to index - populate syllabus.json / pyqs.json first.")
        return

    print(f"Embedding {len(docs)} chunks ({MODEL_NAME})...")
    embeddings = model.encode(docs, show_progress_bar=True).tolist()

    collection.add(
        documents=docs,
        embeddings=embeddings,
        ids=ids,
        metadatas=metadatas,
    )

    print(f"Index built: {len(docs)} chunks -> {INDEX_DIR}")


if __name__ == "__main__":
    main()
