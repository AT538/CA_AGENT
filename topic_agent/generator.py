"""
Given a topic, generates a Mains-ready study summary + model answer,
grounded in two sources:
  - your own uploaded subject study material (topic_agent/sources/, via
    topic_agent/retrieve.py)
  - the UPSC syllabus + 20yr PYQ set (via filter/retrieve.py - the same
    index the daily pipeline and exam_analysis both use)
"""

import yaml
from pathlib import Path

from filter.llm_client import call_with_fallback
from filter.retrieve import retrieve_context, format_context
from topic_agent.retrieve import retrieve_topic_sources

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

GENERATION_PROMPT_TEMPLATE = """You are helping a UPSC Civil Services aspirant prepare for Mains by writing exam-ready material on a specific topic.

TOPIC: {topic}

YOUR OWN UPLOADED STUDY SOURCES (top matches - may be partial or empty, use only what's genuinely relevant):
{source_context}

MATCHED SYLLABUS/PYQ CONTEXT (grounds this topic to the actual syllabus and how UPSC has asked about it before):
{syllabus_context}

Produce Mains-ready material on this topic. Respond ONLY with valid JSON, no markdown fences, no preamble:

{{
  "topic_summary": "a comprehensive study-note-style summary of this topic (8-15 lines) - the core facts, concepts, arguments, and examples an aspirant needs, drawing on the uploaded study sources above wherever they're genuinely relevant. Should be usable as a standalone revision note.",
  "mains_answer": "a complete, ready-to-use Mains-style model answer (~200-250 words) with a clear intro-body-conclusion structure, written the way a topper would actually write it - specific, not generic. Draw concrete facts/examples from the uploaded sources where relevant. If the topic doesn't map to a Mains-style analytical question (e.g. it's pure Prelims trivia), write a concise factual note instead and say so plainly.",
  "syllabus_linkage": ["which syllabus topic(s) this maps to, e.g. 'GS2-Mains: Federalism / Union-State relations'"],
  "relevant_pyqs": ["actual past-year questions from the matched PYQ context above that are on or near this topic - quote them, don't paraphrase"],
  "sources_used": ["which of your uploaded source files/subjects were actually drawn on - an empty list if none of them were relevant"]
}}
"""


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _format_source_context(matches: list[dict]) -> str:
    if not matches:
        return "(no uploaded sources matched - either none dropped yet, or none relevant to this topic)"
    lines = []
    for m in matches:
        meta = m["metadata"]
        tag = f"{meta.get('subject', '?')} / {meta.get('source_file', '?')}"
        lines.append(f"- [{tag}] {m['document'][:300]}")
    return "\n".join(lines)


def generate_topic_answer(topic: str, subject: str | None = None, top_k: int = 6) -> dict:
    """
    Returns: {"topic_summary": str, "mains_answer": str,
              "syllabus_linkage": [...], "relevant_pyqs": [...],
              "sources_used": [...]}
    Falls back to a safe placeholder (with _generated=False) if every
    configured provider fails.
    """
    tier_config = load_config()["topic_agent"]["generation_llm"]

    try:
        source_matches = retrieve_topic_sources(topic, top_k=top_k, subject=subject)
    except RuntimeError as e:
        print(f"[warn] {e}")
        source_matches = []

    syllabus_matches = retrieve_context(topic, top_k=top_k)

    prompt = GENERATION_PROMPT_TEMPLATE.format(
        topic=topic,
        source_context=_format_source_context(source_matches),
        syllabus_context=format_context(syllabus_matches),
    )

    result = call_with_fallback(prompt, tier_config)
    if result is not None:
        return result

    print(f"[error] all generation LLM providers failed for topic '{topic}'")
    return {
        "topic_summary": "",
        "mains_answer": "",
        "syllabus_linkage": [],
        "relevant_pyqs": [],
        "sources_used": [],
        "_generated": False,
    }
