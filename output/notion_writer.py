"""
Writes a daily digest to Notion - a NEW page every day (today.isoformat()
in the title, created fresh each run - never appended to a prior day).

Page layout:
  1. "Quick Summary" - condensed, one-line-per-article key points, grouped
     by syllabus topic, with the syllabus description shown right under
     each topic heading so every point is anchored back to *why* it matters.
  2. "Full Digest" - the detailed listing: source link + 2-3 line note,
     same topic grouping.

Requires:
- NOTION_TOKEN env var (integration token)
- config.yaml -> notion.database_or_page_id set to your target parent
  page (shared with your Notion integration) - each day's page is created
  as a child of this one page, so you get a running list of daily pages.
"""

import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml
from notion_client import Client

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
SYLLABUS_PATH = Path(__file__).parent.parent / "knowledge_base" / "syllabus.json"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def load_syllabus_lookup() -> dict:
    """topic name -> description, so summary points can be anchored to why
    they matter, not just grouped by a bare label."""
    if not SYLLABUS_PATH.exists():
        return {}
    entries = json.loads(SYLLABUS_PATH.read_text())
    return {e["topic"]: e["description"] for e in entries}


def group_by_paper_and_topic(relevant_items: list[dict]) -> dict:
    grouped = defaultdict(lambda: defaultdict(list))
    for item in relevant_items:
        paper = item["judgment"]["gs_paper"]
        topics = item["judgment"]["topics"] or ["General"]
        for topic in topics:
            grouped[paper][topic].append(item)
    return grouped


def _heading(text: str, level: int = 2) -> dict:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": [{"type": "text", "text": {"content": text}}]}}


def _bullet(text: str, url: str | None = None) -> dict:
    text_obj = {"type": "text", "text": {"content": text}}
    if url:
        text_obj["text"]["link"] = {"url": url}
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [text_obj]},
    }


def _bold_bullet(label: str, rest: str) -> dict:
    """Bullet with a bolded lead-in label, e.g. 'Use as example: ' bolded,
    followed by the plain-text content."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [
                {"type": "text", "text": {"content": label}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": rest}},
            ]
        },
    }


def _italic_paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}, "annotations": {"italic": True}}]
        },
    }


def _toggle(title: str, children: list[dict]) -> dict:
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [{"type": "text", "text": {"content": title}}],
            "children": children,
        },
    }


def _exam_angle_toggle(judgment: dict) -> dict | None:
    """Nested toggle holding probable questions, a ready-to-use answer
    example, and where this can be used - kept collapsed so the main list
    stays scannable, but one click away."""
    children = []

    answer_example = judgment.get("answer_example") or ""
    if answer_example:
        children.append(_bold_bullet("Use as example: ", answer_example))

    applicability = judgment.get("applicability") or []
    if applicability:
        children.append(_bullet("Where it can be used: " + "; ".join(applicability)))

    questions = judgment.get("probable_questions") or []
    for q in questions:
        children.append(_bullet(q))

    if not children:
        return None
    return _toggle("Exam angle", children)


def build_summary_blocks(relevant_items: list[dict], syllabus_lookup: dict) -> list[dict]:
    """Section 1 - the main daily read. Contains the actual substance of
    each article (the facts/what happened), grouped by topic, so reading
    this section is meant to replace opening the articles themselves.
    The syllabus description under each topic heading is the only "why this
    matters" framing here - kept separate from the factual summary itself."""
    grouped = group_by_paper_and_topic(relevant_items)
    blocks = [_heading("Quick Summary", level=1)]

    for paper, topics in grouped.items():
        blocks.append(_heading(paper, level=2))
        for topic, items in topics.items():
            blocks.append(_heading(topic, level=3))
            description = syllabus_lookup.get(topic)
            if description:
                blocks.append(_italic_paragraph(f"Syllabus: {description}"))
            for item in items:
                summary = item["judgment"].get("summary") or item["judgment"].get("note", "")
                blocks.append(_bullet(summary, url=item["article"]["url"]))
                exam_angle = _exam_angle_toggle(item["judgment"])
                if exam_angle:
                    blocks.append(exam_angle)

    return blocks


def build_full_digest_blocks(relevant_items: list[dict]) -> list[dict]:
    """Section 2 - reference detail: article title, the same factual
    summary, the syllabus-linkage note, and the source link - for whenever
    you want to trace a point back to its source or see the syllabus tie-in
    explicitly spelled out."""
    grouped = group_by_paper_and_topic(relevant_items)
    blocks = [_heading("Full Digest (with sources)", level=1)]

    for paper, topics in grouped.items():
        blocks.append(_heading(paper, level=2))
        for topic, items in topics.items():
            blocks.append(_heading(topic, level=3))
            for item in items:
                article = item["article"]
                judgment = item["judgment"]
                summary = judgment.get("summary", "")
                relevance = judgment.get("relevance_note", "")
                blocks.append(_bullet(article["title"], url=article["url"]))
                if summary:
                    blocks.append(_italic_paragraph(summary))
                if relevance:
                    blocks.append(_italic_paragraph(f"Why it matters: {relevance}"))
                exam_angle = _exam_angle_toggle(judgment)
                if exam_angle:
                    blocks.append(exam_angle)

    return blocks


def _chunk(blocks: list[dict], size: int = 100) -> list[list[dict]]:
    """Notion's API caps children per request at 100 blocks."""
    return [blocks[i:i + size] for i in range(0, len(blocks), size)]


def publish_digest(relevant_items: list[dict]):
    if not relevant_items:
        print("No relevant items today - skipping Notion write.")
        return

    config = load_config()["notion"]
    client = Client(auth=os.environ["NOTION_TOKEN"])
    syllabus_lookup = load_syllabus_lookup()

    today_title = f"UPSC Current Affairs — {date.today().isoformat()}"

    all_blocks = (
        build_summary_blocks(relevant_items, syllabus_lookup)
        + [{"object": "block", "type": "divider", "divider": {}}]
        + build_full_digest_blocks(relevant_items)
    )
    chunks = _chunk(all_blocks)

    # A brand-new page is created every run - never appended to a prior day.
    page = client.pages.create(
        parent={"page_id": config["database_or_page_id"]},
        properties={"title": [{"type": "text", "text": {"content": today_title}}]},
        children=chunks[0],
    )

    # Append any remaining chunks (only needed on very high-volume days)
    for chunk in chunks[1:]:
        client.blocks.children.append(block_id=page["id"], children=chunk)

    print(f"Published new page '{today_title}' with {len(relevant_items)} items to Notion.")
