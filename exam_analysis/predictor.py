"""
Aggregates every analyzed PYQ (exam_analysis/analyzed_questions.json, built
up across however many `run.py` invocations you've done) into a single
"potential future topics & questions" prediction.

Feeds the LLM a compact frequency summary rather than raw question text, so
this stays cheap even once the cache covers hundreds of questions - and
weights recent years more heavily, per parse_pyqs.py's own tip that the
last 5-8 years predict current exam style far better than very old papers.
"""

import yaml
from collections import Counter
from pathlib import Path

from filter.llm_client import call_with_fallback

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
RECENT_YEARS_WINDOW = 8  # matches parse_pyqs.py's "prioritize last 5-8 years" guidance

PREDICTION_PROMPT_TEMPLATE = """You are helping a UPSC Civil Services aspirant anticipate likely {target_year} exam topics, based on a frequency analysis of {n_questions} previous-year questions ({year_range}) already analyzed for why they were asked.

TOPIC FREQUENCY (all analyzed years, syllabus topic -> times asked):
{topic_freq}

RECENT-YEARS TOPIC FREQUENCY (last {recent_window} years only - weight this more heavily, recent exam style is more predictive):
{recent_topic_freq}

NOTABLE CURRENT-EVENT-DRIVEN QUESTIONS (illustrates UPSC's pattern of turning live developments into questions):
{event_examples}

Based on these patterns, produce a prediction. Respond ONLY with valid JSON, no markdown fences, no preamble:

{{
  "high_probability_topics": ["5-10 syllabus topics most likely to recur in {target_year}, ranked by a combination of frequency and recency - name the specific syllabus topic, not just the paper"],
  "probable_questions": ["8-12 realistic {target_year}-style questions across Prelims and Mains, phrased the way UPSC actually phrases them (Prelims: statement-based; Mains: analytical Discuss/Examine/Critically analyze), covering a mix of the high-probability topics above"],
  "watch_current_events": ["ongoing/recent developments (as of your knowledge) that historically-similar events have turned into questions before, and are plausible {target_year} question seeds"],
  "rationale": "2-4 lines on the overall pattern you see - e.g. which papers lean syllabus-driven vs current-event-driven, any thematic shift in recent years"
}}
"""


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _format_topic_freq(counter: Counter, top_n: int = 25) -> str:
    if not counter:
        return "(no data)"
    return "\n".join(f"- {topic}: {count}" for topic, count in counter.most_common(top_n))


def build_prediction(analyzed: list[dict], target_year: int) -> dict:
    """
    analyzed: list of cached analysis entries, each a merged
    {**question, **analysis} dict (year, paper, question, syllabus_topics,
    trigger, trigger_note, why_asked, ...) - i.e. cache.load_cache().values().

    Returns: {"high_probability_topics": [...], "probable_questions": [...],
              "watch_current_events": [...], "rationale": str}
    """
    if not analyzed:
        return {
            "high_probability_topics": [],
            "probable_questions": [],
            "watch_current_events": [],
            "rationale": "No analyzed questions yet - run analysis on at least one paper first.",
        }

    years = [a["year"] for a in analyzed]
    year_range = f"{min(years)}-{max(years)}"
    recent_cutoff = max(years) - RECENT_YEARS_WINDOW

    all_topics = Counter()
    recent_topics = Counter()
    event_examples = []

    for a in analyzed:
        for topic in a.get("syllabus_topics", []):
            all_topics[topic] += 1
            if a["year"] >= recent_cutoff:
                recent_topics[topic] += 1
        if a.get("trigger") in ("current_event", "both") and a.get("trigger_note"):
            event_examples.append(f"[{a['year']} {a['paper']}] {a['question'][:120]} -> {a['trigger_note']}")

    prompt = PREDICTION_PROMPT_TEMPLATE.format(
        target_year=target_year,
        n_questions=len(analyzed),
        year_range=year_range,
        topic_freq=_format_topic_freq(all_topics),
        recent_window=RECENT_YEARS_WINDOW,
        recent_topic_freq=_format_topic_freq(recent_topics),
        event_examples="\n".join(event_examples[-30:]) or "(none flagged)",
    )

    tier_config = load_config()["exam_analysis"]["prediction_llm"]
    result = call_with_fallback(prompt, tier_config)
    if result is not None:
        return result

    print("[error] all prediction LLM providers failed")
    return {
        "high_probability_topics": [],
        "probable_questions": [],
        "watch_current_events": [],
        "rationale": "",
    }
