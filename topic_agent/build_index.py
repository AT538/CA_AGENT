"""
Builds/rebuilds the topic_sources embedding index from every file dropped
into topic_agent/sources/<Subject>/ - a full rebuild each time (same
pattern as knowledge_base/build_syllabus_index.py), since this indexes a
fixed set of user-curated study material, not a growing daily stream.

Run this LOCALLY whenever you add/remove/change a source file. Supported
formats: .pdf, .txt, .md. This must run locally, not in CI - the raw
source files are gitignored (see ../SKILL.md for why), so a CI runner
never has them and would only ever see an empty sources/ directory.

Refuses to touch the existing index if sources/ turns up empty (no files
yet, or an accidental empty run) - see SKILL.md's note on this being a
deliberate safety check, not an oversight.
"""

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from ingest.pdf_utils import extract_pdf_text, chunk_words

BASE_DIR = Path(__file__).parent
SOURCES_DIR = BASE_DIR / "sources"
INDEX_DIR = BASE_DIR / "index"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
CHUNK_WORD_COUNT = 500
SUPPORTED_SUFFIXES = (".pdf", ".txt", ".md")


def _extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return extract_pdf_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def collect_chunks() -> tuple[list[str], list[str], list[dict]]:
    docs, ids, metadatas = [], [], []
    if not SOURCES_DIR.exists():
        return docs, ids, metadatas

    for subject_dir in sorted(p for p in SOURCES_DIR.iterdir() if p.is_dir()):
        subject = subject_dir.name
        for source_path in sorted(subject_dir.glob("*")):
            if source_path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                text = _extract_text(source_path)
            except Exception as e:
                print(f"  [error] couldn't read {source_path.name}: {e}")
                continue

            chunks = chunk_words(text, CHUNK_WORD_COUNT)
            for i, chunk in enumerate(chunks):
                docs.append(chunk)
                ids.append(f"{subject}-{source_path.stem}-{i}")
                metadatas.append({"subject": subject, "source_file": source_path.name, "chunk_index": i})
            print(f"  {subject}/{source_path.name}: {len(chunks)} chunks")

    return docs, ids, metadatas


def main():
    print(f"Scanning {SOURCES_DIR} for subject source files (.pdf/.txt/.md)...")
    docs, ids, metadatas = collect_chunks()

    if not docs:
        print(f"\nNo source files found under {SOURCES_DIR}/<Subject>/*.{{pdf,txt,md}}.")
        print("Drop some in (one folder per subject), then re-run this. "
              "Leaving any existing index untouched.")
        return

    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=str(INDEX_DIR))

    if "topic_sources" in [c.name for c in client.list_collections()]:
        client.delete_collection("topic_sources")
    collection = client.create_collection("topic_sources")

    print(f"\nEmbedding {len(docs)} chunks ({MODEL_NAME})...")
    embeddings = model.encode(docs, show_progress_bar=True).tolist()
    collection.add(documents=docs, embeddings=embeddings, ids=ids, metadatas=metadatas)

    subjects = sorted(set(m["subject"] for m in metadatas))
    print(f"\nIndex built: {len(docs)} chunks across {len(subjects)} subject(s) -> {INDEX_DIR}")
    print(f"Subjects: {', '.join(subjects)}")
    print("\nCommit topic_agent/index/ to git - it's what --topic generation "
          "actually reads, both locally and in CI.")


if __name__ == "__main__":
    main()
