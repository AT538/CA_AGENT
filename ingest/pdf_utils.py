"""
Shared PDF text extraction + word-count chunking primitives, used by
ingest/monthly_pdfs.py, knowledge_base/parse_pyqs.py, and topic_agent/
build_index.py - so the same ~10 lines aren't reimplemented three times.
"""

from pathlib import Path

import pdfplumber


def extract_pdf_text(pdf_path: Path) -> str:
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def chunk_words(text: str, chunk_word_count: int = 500, min_words: int = 50) -> list[str]:
    """Splits text into ~chunk_word_count-word pieces, dropping trailing
    scraps shorter than min_words."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_word_count):
        chunk = words[i:i + chunk_word_count]
        if len(chunk) < min_words:
            continue
        chunks.append(" ".join(chunk))
    return chunks
