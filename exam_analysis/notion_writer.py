"""
Publishes PYQ trend-analysis output to a dedicated Notion page - separate
from the daily current-affairs digest (output/notion_writer.py), since this
is on-demand/cumulative rather than a daily fresh page.

Each run creates one new page containing:
  1. The refreshed prediction for the target year, built from every
     question analyzed so far (not just this run)
  2. This run's own per-question analysis (why each question was asked)

Requires:
- NOTION_TOKEN env var (same integration as the daily digest)
- config.yaml -> notion.exam_analysis_page_id set to a page shared with
  your Notion integration (separate from the daily digest's page, so the
  two don't mix)
"""

import os
from datetime import date
from pathlib import Path

import yaml
from notion_client import Client

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _heading(text: str, level: int = 2) -> dict:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _bullet(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _paragraph(text: str, italic: bool = False) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}, "annotations": {"italic": italic}}]},
    }


def build_prediction_blocks(prediction: dict, target_year: int, total_analyzed: int) -> list[dict]:
    blocks = [_heading(f"Potential {target_year} Topics & Questions (from {total_analyzed} analyzed PYQs)", level=1)]

    topics = prediction.get("high_probability_topics", [])
    if topics:
        blocks.append(_heading("High-probability topics", level=2))
        for t in topics:
            blocks.append(_bullet(t))

    questions = prediction.get("probable_questions", [])
    if questions:
        blocks.append(_heading("Probable questions", level=2))
        for q in questions:
            blocks.append(_bullet(q))

    events = prediction.get("watch_current_events", [])
    if events:
        blocks.append(_heading("Current events to watch", level=2))
        for e in events:
            blocks.append(_bullet(e))

    if prediction.get("rationale"):
        blocks.append(_heading("Rationale", level=2))
        blocks.append(_paragraph(prediction["rationale"]))

    return blocks


def build_analysis_blocks(analyses: list[dict], year, paper) -> list[dict]:
    if not analyses:
        return []
    label = f"{year} - {paper}" if year and paper else "this run"
    blocks = [_heading(f"Question Analysis — {label}", level=1)]

    for a in sorted(analyses, key=lambda x: x.get("_index", 0)):
        blocks.append(_heading(f"Q: {a['question'][:100]}", level=3))
        blocks.append(_paragraph(a["question"]))
        topics = ", ".join(a.get("syllabus_topics", [])) or "—"
        blocks.append(_bullet(f"Syllabus topic(s): {topics}"))
        blocks.append(_bullet(f"Trigger: {a.get('trigger', 'unknown')}"))
        if a.get("trigger_note"):
            blocks.append(_paragraph(a["trigger_note"], italic=True))
        if a.get("why_asked"):
            blocks.append(_paragraph(f"Why asked: {a['why_asked']}"))

    return blocks


def _chunk(blocks: list[dict], size: int = 100) -> list[list[dict]]:
    """Notion's API caps children per request at 100 blocks."""
    return [blocks[i:i + size] for i in range(0, len(blocks), size)]


def publish_analysis(analyses: list[dict], prediction: dict, target_year: int,
                      year, paper, total_analyzed: int):
    config = load_config()["notion"]
    page_id = config.get("exam_analysis_page_id")
    if not page_id:
        print("[warn] notion.exam_analysis_page_id not set in config.yaml - skipping Notion publish.")
        print("Set it to a page shared with your Notion integration "
              "(same NOTION_TOKEN as the daily digest, different page).")
        return

    all_blocks = build_prediction_blocks(prediction, target_year, total_analyzed)
    analysis_blocks = build_analysis_blocks(analyses, year, paper)
    if analysis_blocks:
        all_blocks += [{"object": "block", "type": "divider", "divider": {}}] + analysis_blocks

    if not all_blocks:
        print("Nothing to publish.")
        return

    client = Client(auth=os.environ["NOTION_TOKEN"])
    label = f"{year} {paper}" if year and paper else "prediction refresh"
    title = f"PYQ Analysis — {label} — {date.today().isoformat()}"

    chunks = _chunk(all_blocks)
    page = client.pages.create(
        parent={"page_id": page_id},
        properties={"title": [{"type": "text", "text": {"content": title}}]},
        children=chunks[0],
    )
    for chunk in chunks[1:]:
        client.blocks.children.append(block_id=page["id"], children=chunk)

    print(f"Published '{title}' to Notion.")
