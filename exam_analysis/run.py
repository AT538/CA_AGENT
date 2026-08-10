"""
On-demand CLI: analyze one or more UPSC PYQ papers - for each question, why
it was asked (syllabus-driven, current-event-driven, or both) - and refresh
the cumulative "potential {target-year} topics & questions" prediction
across everything analyzed so far. Publishes both to a dedicated Notion page.

Usage:
  python -m exam_analysis.run --year 2023 --paper mains_gs2
  python -m exam_analysis.run --year 2023 --paper all         # every paper for that year
  python -m exam_analysis.run --all                           # every year x paper in pyqs.json
  python -m exam_analysis.run --predict-only                  # skip analysis, just refresh the prediction
  python -m exam_analysis.run --year 2023 --paper mains_gs2 --limit 5    # cap new LLM calls (testing)
  python -m exam_analysis.run --year 2023 --paper mains_gs2 --force      # re-analyze even if cached
  python -m exam_analysis.run --all --target-year 2028

Prerequisite: knowledge_base/pyqs.json must exist - populate it first via
knowledge_base/fetch_pyqs.py (download PDFs, or drop them into
knowledge_base/pyqs/raw/ manually) then knowledge_base/parse_pyqs.py
(parses the PDFs into pyqs.json).
"""

import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from exam_analysis.analyzer import analyze_question
from exam_analysis.cache import load_cache, save_cache, question_id
from exam_analysis.predictor import build_prediction
from exam_analysis.notion_writer import publish_analysis
from filter.retrieve import retrieve_context

PYQS_PATH = Path(__file__).parent.parent / "knowledge_base" / "pyqs.json"
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

VALID_PAPERS = ["prelims_gs1", "mains_gs1", "mains_gs2", "mains_gs3", "mains_gs4"]


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def load_questions() -> list[dict]:
    if not PYQS_PATH.exists():
        print(f"[error] {PYQS_PATH} not found.")
        print("Run knowledge_base/fetch_pyqs.py to download question paper PDFs "
              "(or drop them manually into knowledge_base/pyqs/raw/), then "
              "knowledge_base/parse_pyqs.py to parse them into pyqs.json.")
        sys.exit(1)

    questions = json.loads(PYQS_PATH.read_text(encoding="utf-8"))
    # Stable per-paper index, in file order - matches the cache key scheme.
    counters = {}
    for q in questions:
        key = (q["year"], q["paper"])
        counters[key] = counters.get(key, -1) + 1
        q["_index"] = counters[key]
    return questions


def select_questions(questions: list[dict], year: int | None, paper: str | None) -> list[dict]:
    selected = questions
    if year is not None:
        selected = [q for q in selected if q["year"] == year]
    if paper is not None and paper != "all":
        selected = [q for q in selected if q["paper"] == paper]
    return selected


def run_analysis(selected: list[dict], limit: int | None, force: bool) -> dict:
    """Analyzes `selected`, skipping already-cached entries unless
    force=True, capped at `limit` NEW LLM calls this invocation. Returns
    the FULL cache (everything analyzed across all past runs, not just this
    subset) so the prediction step sees the complete picture."""
    cache = load_cache()
    top_k = load_config().get("retrieval", {}).get("top_k", 6)
    new_calls = 0

    for q in selected:
        qid = question_id(q, q["_index"])
        if qid in cache and not force:
            continue
        if limit is not None and new_calls >= limit:
            print(f"[limit] reached --limit {limit} new analyses - remaining questions "
                  f"stay uncached, pick them up on a later run")
            break

        text = f"{q['paper']} {q['question']}"
        context_matches = retrieve_context(text, top_k=top_k)
        analysis = analyze_question(q, context_matches)
        q_data = {k: v for k, v in q.items() if k != "_index"}
        cache[qid] = {**q_data, "_index": q["_index"], **analysis}
        new_calls += 1

        status = "ok" if analysis.get("_analyzed", True) else "failed"
        print(f"  [{status}] {q['year']} {q['paper']} -> {analysis.get('syllabus_topics')}")

    save_cache(cache)
    print(f"\nAnalyzed {new_calls} new question(s) this run.")
    return cache


def main():
    parser = argparse.ArgumentParser(description="Analyze UPSC PYQ papers and predict likely future topics")
    parser.add_argument("--year", type=int, help="Exam year, e.g. 2023")
    parser.add_argument("--paper", choices=VALID_PAPERS + ["all"], help="Paper, or 'all' for every paper in --year")
    parser.add_argument("--all", action="store_true", help="Analyze every year x paper in pyqs.json")
    parser.add_argument("--predict-only", action="store_true",
                         help="Skip analysis, just refresh the prediction from the existing cache")
    parser.add_argument("--target-year", type=int, default=2027, help="Exam year to predict for (default 2027)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Cap on NEW LLM analysis calls this run (testing/quota safety)")
    parser.add_argument("--force", action="store_true", help="Re-analyze even if already cached")
    args = parser.parse_args()

    if not args.predict_only and not args.all and (args.year is None or args.paper is None):
        parser.error("Specify --year and --paper (--paper all for every paper that year), or --all, or --predict-only")

    selected = []
    if args.predict_only:
        cache = load_cache()
    else:
        questions = load_questions()
        selected = questions if args.all else select_questions(questions, args.year, args.paper)
        if not selected:
            print(f"No questions found for year={args.year} paper={args.paper} in {PYQS_PATH}")
            sys.exit(1)
        print(f"=== Analyzing {len(selected)} question(s) ===\n")
        cache = run_analysis(selected, args.limit, args.force)

    print(f"\n=== Refreshing {args.target_year} prediction from {len(cache)} cached analyses ===")
    prediction = build_prediction(list(cache.values()), args.target_year)

    this_run_ids = {question_id(q, q["_index"]) for q in selected}
    this_run_analyses = [v for k, v in cache.items() if k in this_run_ids]

    publish_analysis(this_run_analyses, prediction, args.target_year, args.year, args.paper, total_analyzed=len(cache))
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
