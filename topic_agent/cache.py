"""
Local cache of generated topic answers, keyed by a normalized
"<subject|_>::<topic>" string. Generation costs real LLM quota, so
re-requesting the same topic just republishes the cached result unless
--force is passed.
"""

import json
import re
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "generated_topics.json"


def normalize_key(topic: str, subject: str | None) -> str:
    slug = re.sub(r"\s+", " ", topic.strip().lower())
    return f"{(subject or '_').strip().lower()}::{slug}"


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def save_cache(cache: dict):
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
