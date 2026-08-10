"""
On-demand CLI: generate a Mains-ready study summary + model answer for a
topic, grounded in your own uploaded subject sources plus the UPSC
syllabus/PYQ set, and publish it to Notion.

Usage:
  python -m topic_agent.run --topic "Federalism in India"
  python -m topic_agent.run --topic "Green Hydrogen Mission" --subject Environment
  python -m topic_agent.run --topic "Federalism in India" --force   # regenerate even if cached
  python -m topic_agent.run --rebuild-index                          # re-embed topic_agent/sources/ (LOCAL ONLY)
  python -m topic_agent.run --list-subjects                           # show ingested subjects/files

Prerequisite: drop your own study material into topic_agent/sources/<Subject>/
(.pdf/.txt/.md), then run --rebuild-index before your first --topic run.
Without that, generation still works, using syllabus/PYQ grounding only.
"""

import argparse
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

import topic_agent.build_index as build_index
from topic_agent.cache import load_cache, save_cache, normalize_key
from topic_agent.generator import generate_topic_answer
from topic_agent.notion_writer import publish_topic

SOURCES_DIR = Path(__file__).parent / "sources"
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
SUPPORTED_SUFFIXES = (".pdf", ".txt", ".md")


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def list_subjects():
    if not SOURCES_DIR.exists():
        print(f"{SOURCES_DIR} doesn't exist yet - create a subject folder and drop files in, "
              f"e.g. {SOURCES_DIR / 'Polity' / 'laxmikanth_ch5.pdf'}")
        return

    found = False
    for subject_dir in sorted(p for p in SOURCES_DIR.iterdir() if p.is_dir()):
        files = [f for f in subject_dir.glob("*") if f.suffix.lower() in SUPPORTED_SUFFIXES]
        if files:
            found = True
            print(f"{subject_dir.name}: {len(files)} file(s)")
            for f in files:
                print(f"  - {f.name}")

    if not found:
        print(f"No source files found under {SOURCES_DIR}/<Subject>/*.{{pdf,txt,md}}")


def main():
    parser = argparse.ArgumentParser(description="Generate a Mains-ready topic summary + model answer")
    parser.add_argument("--topic", type=str, help="Topic to generate material for")
    parser.add_argument("--subject", type=str, default=None,
                         help="Optional: restrict retrieval to one subject's uploaded sources")
    parser.add_argument("--force", action="store_true", help="Regenerate even if already cached")
    parser.add_argument("--rebuild-index", action="store_true",
                         help="Re-embed everything in topic_agent/sources/ - LOCAL ONLY, "
                              "source files are gitignored so this is a no-op in CI")
    parser.add_argument("--list-subjects", action="store_true", help="List ingested subjects and their source files")
    args = parser.parse_args()

    if args.rebuild_index:
        build_index.main()
        return

    if args.list_subjects:
        list_subjects()
        return

    if not args.topic:
        parser.error("Specify --topic, or --rebuild-index, or --list-subjects")

    cache = load_cache()
    key = normalize_key(args.topic, args.subject)

    if key in cache and not args.force:
        print("Already generated (use --force to regenerate) - republishing the cached result to Notion.")
        result = cache[key]
    else:
        top_k = load_config().get("retrieval", {}).get("top_k", 6)
        label = args.topic + (f" (subject: {args.subject})" if args.subject else "")
        print(f"Generating material for topic: {label}")
        result = generate_topic_answer(args.topic, subject=args.subject, top_k=top_k)
        cache[key] = result
        save_cache(cache)

    publish_topic(args.topic, result, subject=args.subject)


if __name__ == "__main__":
    main()
