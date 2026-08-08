"""
Seen-articles store (SQLite) - dedup so the pipeline never reprocesses
the same article twice across daily runs.
"""

import hashlib
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "articles.db"


def _hash(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}|{title}".encode()).hexdigest()


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_articles (
            hash TEXT PRIMARY KEY,
            url TEXT,
            title TEXT,
            source TEXT,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            relevant INTEGER DEFAULT 0
        )
    """)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_seen(url: str, title: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_articles WHERE hash = ?", (_hash(url, title),)
        ).fetchone()
        return row is not None


def mark_seen(url: str, title: str, source: str, relevant: bool = False):
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_articles (hash, url, title, source, relevant) "
            "VALUES (?, ?, ?, ?, ?)",
            (_hash(url, title), url, title, source, int(relevant)),
        )


def filter_new(articles: list[dict]) -> list[dict]:
    """Given a list of {url, title, ...} dicts, return only the unseen ones."""
    return [a for a in articles if not is_seen(a["url"], a["title"])]
