"""
Daily orchestrator: ingest -> dedupe -> filter/judge -> publish.

Run manually with `python main.py`, or via the GitHub Actions daily workflow.
"""

import sys
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ingest.feeds import fetch_all_rss
from ingest.scrapers import fetch_all_scraped
from ingest.monthly_pdfs import fetch_auto_sources, parse_all_pdfs
from ingest.dedupe import filter_new, mark_seen
from filter.retrieve import retrieve_context
from filter.judge import judge_relevance, generate_exam_angle
from output.notion_writer import publish_digest

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def run():
    print("=== UPSC Current Affairs Agent - daily run ===\n")
    top_k = yaml.safe_load(CONFIG_PATH.read_text()).get("retrieval", {}).get("top_k", 5)

    print("Step 1: Ingesting daily sources (RSS + scraped)...")
    articles = fetch_all_rss() + fetch_all_scraped()

    print("\nStep 1b: Checking monthly/annual PDF sources "
          "(Yojana, Kurukshetra, PRS Monthly Policy Review, Vision IAS, Budget, Economic Survey)...")
    fetch_auto_sources()
    articles += parse_all_pdfs()

    print("\nStep 2: Filtering out already-seen items...")
    new_articles = filter_new(articles)
    print(f"{len(new_articles)} new items to evaluate (of {len(articles)} total)")

    print("\nStep 3: Retrieving context + judging relevance (Tier 1 - cheap, every item)...")
    relevant_items = []
    for article in new_articles:
        text = f"{article['title']} {article.get('summary', '')}"
        context_matches = retrieve_context(text, top_k=top_k)
        judgment = judge_relevance(article, context_matches)

        if not judgment.get("_judged", True):
            # LLM providers were all unavailable (e.g. quota exhausted) - don't
            # mark seen, so this article gets a real judgment on the next run
            # instead of being silently discarded as "not relevant" forever.
            print(f"  [retry-later] {article['title'][:70]}")
            continue

        mark_seen(article["url"], article["title"], article["source"], judgment["relevant"])

        if judgment["relevant"]:
            relevant_items.append({"article": article, "judgment": judgment, "context": context_matches})
            print(f"  [RELEVANT] {article['title'][:70]} -> {judgment['gs_paper']}")
        else:
            print(f"  [skip] {article['title'][:70]}")

    print(f"\n{len(relevant_items)} relevant items found today")

    print("\nStep 3b: Generating exam angle (Tier 2 - only for relevant items)...")
    for item in relevant_items:
        exam_angle = generate_exam_angle(item["article"], item["judgment"], item["context"])
        item["judgment"].update(exam_angle)

    print("\nStep 4: Publishing digest...")
    publish_digest(relevant_items)

    print("\n=== Done ===")


if __name__ == "__main__":
    run()
