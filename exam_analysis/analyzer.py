"""
Per-question analysis: for a single PYQ, ask the LLM to explain why it was
asked - syllabus-driven, current-event-driven, or both.

The syllabus side is grounded against the local syllabus/PYQ embedding index
(filter.retrieve), same as the daily pipeline. The "was there a current
event around that year" side leans entirely on the model's own training
knowledge - there's no local database of past years' news to check against,
so trigger_note should be read as a plausible hypothesis, not a verified
citation.
"""

import yaml
from pathlib import Path

from filter.llm_client import call_with_fallback
from filter.retrieve import format_context

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

ANALYSIS_PROMPT_TEMPLATE = """You are analyzing a UPSC Civil Services exam question to understand WHY it was asked, for a student building exam-pattern intuition.

QUESTION ({paper}, {year}):
{question}

MATCHED SYLLABUS/PYQ CONTEXT (top candidates from the syllabus and other PYQs - may or may not be a good fit):
{context}

Analyze this question. Respond ONLY with valid JSON, no markdown fences, no preamble:

{{
  "syllabus_topics": ["the specific syllabus topic(s) this question maps to"],
  "trigger": "syllabus" | "current_event" | "both",
  "trigger_note": "1-3 lines: if syllabus-driven, which static-syllabus theme and why UPSC tends to ask this; if current-event-driven, name the specific event/development around {year} that plausibly prompted this if you know it - clearly flag if you're not confident of the specific event rather than guessing one",
  "why_asked": "1-2 lines on the underlying exam-setting logic - e.g. a recurring theme, testing conceptual clarity vs application, or linking two topics together"
}}
"""


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def analyze_question(question: dict, context_matches: list) -> dict:
    """
    question: {"year": int, "paper": str, "question": str, "marks": int|None}
    context_matches: output of filter.retrieve.retrieve_context()

    Returns: {"syllabus_topics": [...], "trigger": str, "trigger_note": str,
              "why_asked": str}
    Falls back to a safe placeholder (with _analyzed=False) if every
    configured provider fails, so a bad API day doesn't crash a whole
    paper's worth of analysis - the caller can retry that question later.
    """
    tier_config = load_config()["exam_analysis"]["analysis_llm"]
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        paper=question["paper"],
        year=question["year"],
        question=question["question"],
        context=format_context(context_matches),
    )

    result = call_with_fallback(prompt, tier_config)
    if result is not None:
        return result

    print(f"[error] all analysis LLM providers failed for {question['year']} {question['paper']} - skipping")
    return {
        "syllabus_topics": [],
        "trigger": "unknown",
        "trigger_note": "",
        "why_asked": "",
        "_analyzed": False,
    }
