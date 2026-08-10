"""
Local cache of per-question PYQ analysis, keyed by a stable id
(<year>_<paper>_<index-within-that-paper>). LLM analysis costs real
free-tier quota, so every result is cached here - re-running an
already-analyzed year/paper costs nothing unless --force is passed.
"""

import json
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "analyzed_questions.json"


def question_id(question: dict, index: int) -> str:
    return f"{question['year']}_{question['paper']}_{index}"


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
