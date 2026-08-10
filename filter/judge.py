"""
Two-tier LLM judgment:

TIER 1 - judge_relevance(): runs on EVERY incoming item. Cheap/fast free-tier
model (e.g. Groq Llama 3.3, Gemini Flash). Decides relevance and produces
the factual summary + syllabus linkage. High volume, so this must stay
free/cheap.

TIER 2 - generate_exam_angle(): runs ONLY on items already marked relevant
by Tier 1 - a much smaller set. Produces the harder, more generative fields
(probable exam questions, where it's applicable, a ready-to-cite answer
example). Since volume here is a fraction of Tier 1's, this tier can point
at a stronger model (still free-tier by default, but configured separately
in config.yaml -> llm.exam_angle so it's easy to bump to something stronger,
including a paid model occasionally, without touching Tier 1's cost profile).

Both tiers are provider-agnostic through filter.llm_client's shared provider
registry - swap models/providers per tier in config.yaml, no code changes needed.
"""

import yaml
from pathlib import Path

from filter.llm_client import call_with_fallback
from filter.retrieve import format_context

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

RELEVANCE_PROMPT_TEMPLATE = """You are helping a UPSC Civil Services aspirant filter daily/periodic reading for exam relevance, across BOTH Prelims and Mains (GS1-4, Ethics, Essay).

ARTICLE:
Title: {title}
Summary: {summary}

MATCHED SYLLABUS/PYQ CONTEXT (top candidates from Prelims + Mains syllabus and 20 years of Prelims + Mains PYQs, may or may not be a good fit):
{context}

Decide if this article is genuinely relevant to UPSC preparation. Respond ONLY with valid JSON, no markdown fences, no preamble:

{{
  "relevant": true or false,
  "gs_paper": "GS1" | "GS2" | "GS3" | "GS4" | "Prelims-only" | "Essay" | "Not relevant",
  "topics": ["topic1", "topic2"],
  "summary": "3-5 line PLAIN-LANGUAGE summary of the actual content of the article - the facts, numbers, names, what happened, what was announced/decided. Written so that reading this line is enough - the person should NOT need to open the article to get the substance. No fluff, no 'this article discusses...' framing - just the information itself.",
  "relevance_note": "ONE short line: why/how this connects to the syllabus topic or a PYQ pattern - separate from the summary, purely the syllabus linkage"
}}
"""

EXAM_ANGLE_PROMPT_TEMPLATE = """You are helping a UPSC Civil Services aspirant extract exam-usable material from an article already confirmed relevant to their preparation.

ARTICLE:
Title: {title}

FACTUAL SUMMARY (already extracted):
{summary}

SYLLABUS LINKAGE: {gs_paper} - {topics}
{relevance_note}

MATCHED SYLLABUS/PYQ CONTEXT:
{context}

Produce exam-usable material. Respond ONLY with valid JSON, no markdown fences, no preamble:

{{
  "probable_questions": ["1-3 realistic exam-style questions this article's content could seed - phrase them the way UPSC actually phrases questions (Prelims: statement-based 'Consider the following statements' style if applicable; Mains: analytical 'Discuss/Examine/Critically analyze' style)"],
  "applicability": ["Where this could actually be used when answering - e.g. 'GS2 Mains (Governance)', 'Prelims (Polity)', 'Essay (if topic is about federalism/technology/etc.)', 'GS4 Ethics case study (illustrative example for integrity/accountability)'. Be specific and only include genuinely plausible uses - don't pad this list."],
  "answer_example": "A ready-to-use example/illustration drawn from THIS article's specific facts, written the way a topper would drop it into a Mains or Essay answer as supporting evidence - e.g. 'Example: the 2026 X scheme's Y outcome illustrates Z principle.' Must reference the actual names/numbers/facts from the article, not a generic statement. If the article genuinely has nothing citable as an example (e.g. it's pure Prelims trivia with no illustrative value), return an empty string."
}}
"""


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def judge_relevance(article: dict, context_matches: list) -> dict:
    """
    TIER 1 - runs on every incoming item.

    article: {"title": ..., "summary": ...}
    context_matches: output of filter.retrieve.retrieve_context()

    Returns: {"relevant": bool, "gs_paper": str, "topics": [...],
              "summary": str, "relevance_note": str}
    Falls back to fallback_provider on primary failure; returns a safe
    default (relevant=False) if both fail, so a bad API day never crashes
    the whole pipeline.
    """
    tier_config = load_config()["llm"]
    prompt = RELEVANCE_PROMPT_TEMPLATE.format(
        title=article.get("title", ""),
        summary=article.get("summary", ""),
        context=format_context(context_matches),
    )

    result = call_with_fallback(prompt, tier_config)
    if result is not None:
        return result

    print("[error] all Tier 1 LLM providers failed - defaulting to not-relevant")
    return {
        "relevant": False,
        "gs_paper": "Not relevant",
        "topics": [],
        "summary": "",
        "relevance_note": "",
        "_judged": False,
    }


def generate_exam_angle(article: dict, judgment: dict, context_matches: list) -> dict:
    """
    TIER 2 - runs ONLY on items already marked relevant by judge_relevance().
    Since this only sees the relevant subset (a fraction of Tier 1's volume),
    it's configured separately (config.yaml -> llm.exam_angle) so you can
    point it at a stronger model without inflating Tier 1's cost.

    Returns: {"probable_questions": [...], "applicability": [...], "answer_example": str}
    Defaults to empty values on failure - a missing exam angle degrades the
    digest gracefully rather than dropping the whole item.
    """
    config = load_config()["llm"]
    tier_config = config.get("exam_angle", config)  # fall back to Tier 1's config if unset

    prompt = EXAM_ANGLE_PROMPT_TEMPLATE.format(
        title=article.get("title", ""),
        summary=judgment.get("summary", ""),
        gs_paper=judgment.get("gs_paper", ""),
        topics=", ".join(judgment.get("topics", [])),
        relevance_note=judgment.get("relevance_note", ""),
        context=format_context(context_matches),
    )

    result = call_with_fallback(prompt, tier_config)
    if result is not None:
        return result

    print("[error] all Tier 2 (exam angle) LLM providers failed - leaving exam angle empty")
    return {"probable_questions": [], "applicability": [], "answer_example": ""}
