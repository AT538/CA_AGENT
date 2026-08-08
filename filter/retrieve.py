"""
Stage 1 of relevance filtering: embed an article and retrieve the top-k
most similar syllabus/PYQ chunks from the local Chroma index.

This narrows the field before the LLM judging step (filter/judge.py),
which is what lets a free-tier model do a good enough job in stage 2.
"""

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

INDEX_DIR = Path(__file__).parent.parent / "knowledge_base" / "index"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(INDEX_DIR))
        _collection = client.get_collection("upsc_knowledge")
    return _collection


def retrieve_context(article_text: str, top_k: int = 5) -> list[dict]:
    """
    Returns the top_k most relevant syllabus/PYQ chunks for a given
    article, as a list of {document, metadata, distance}.
    """
    model = _get_model()
    collection = _get_collection()

    embedding = model.encode([article_text]).tolist()
    results = collection.query(query_embeddings=embedding, n_results=top_k)

    matches = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        matches.append({"document": doc, "metadata": meta, "distance": dist})
    return matches


if __name__ == "__main__":
    sample = "The RBI announced a revision to the repo rate citing inflation concerns."
    for m in retrieve_context(sample):
        print(f"[{m['distance']:.3f}] {m['metadata']} -> {m['document'][:80]}")
