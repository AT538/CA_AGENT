"""
Embedding retrieval over the topic_sources index (built by build_index.py)
- your own uploaded subject study material. Mirrors filter/retrieve.py's
shape exactly, but points at a separate index/collection, since this is a
different, user-curated corpus, not the fixed syllabus+PYQ set.
"""

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

INDEX_DIR = Path(__file__).parent / "index"
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
        _collection = client.get_collection("topic_sources")
    return _collection


def retrieve_topic_sources(query_text: str, top_k: int = 6, subject: str | None = None) -> list[dict]:
    """
    Returns the top_k most relevant uploaded-source chunks for a topic
    query, as {document, metadata, distance}.

    Raises RuntimeError if the index hasn't been built yet (see
    build_index.py) - callers should catch this and degrade gracefully
    (syllabus/PYQ grounding still works without it) rather than crash.
    """
    model = _get_model()
    try:
        collection = _get_collection()
    except Exception as e:
        raise RuntimeError(
            "topic_agent index not found or empty - run "
            "`python -m topic_agent.run --rebuild-index` locally after dropping "
            "source files into topic_agent/sources/<Subject>/"
        ) from e

    embedding = model.encode([query_text]).tolist()
    where = {"subject": subject} if subject else None
    results = collection.query(query_embeddings=embedding, n_results=top_k, where=where)

    matches = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        matches.append({"document": doc, "metadata": meta, "distance": dist})
    return matches
