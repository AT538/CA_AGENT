"""
Publishes a generated topic answer to a dedicated Notion page - separate
from both the daily digest (output/notion_writer.py) and exam_analysis's
page, since this is a third, independent output stream.

Requires:
- NOTION_TOKEN env var (same integration as the other two writers)
- config.yaml -> notion.topic_agent_page_id set to a page shared with your
  Notion integration (different from the other two page ids)
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


def _paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def build_blocks(topic: str, result: dict) -> list[dict]:
    blocks = [_heading(topic, level=1)]

    linkage = result.get("syllabus_linkage", [])
    if linkage:
        blocks.append(_heading("Syllabus linkage", level=3))
        for l in linkage:
            blocks.append(_bullet(l))

    if result.get("topic_summary"):
        blocks.append(_heading("Topic Summary", level=2))
        blocks.append(_paragraph(result["topic_summary"]))

    if result.get("mains_answer"):
        blocks.append(_heading("Mains Model Answer", level=2))
        blocks.append(_paragraph(result["mains_answer"]))

    pyqs = result.get("relevant_pyqs", [])
    if pyqs:
        blocks.append(_heading("Relevant PYQs", level=3))
        for q in pyqs:
            blocks.append(_bullet(q))

    sources = result.get("sources_used", [])
    if sources:
        blocks.append(_heading("Sources used", level=3))
        for s in sources:
            blocks.append(_bullet(s))

    return blocks


def _chunk(blocks: list[dict], size: int = 100) -> list[list[dict]]:
    """Notion's API caps children per request at 100 blocks."""
    return [blocks[i:i + size] for i in range(0, len(blocks), size)]


def publish_topic(topic: str, result: dict, subject: str | None = None):
    config = load_config()["notion"]
    page_id = config.get("topic_agent_page_id")
    if not page_id:
        print("[warn] notion.topic_agent_page_id not set in config.yaml - skipping Notion publish.")
        print("Set it to a page shared with your Notion integration "
              "(same NOTION_TOKEN as the other outputs, a different page).")
        return

    blocks = build_blocks(topic, result)
    if not blocks or len(blocks) == 1:  # only the title heading, nothing else
        print("Nothing substantive to publish (generation likely failed).")
        return

    client = Client(auth=os.environ["NOTION_TOKEN"])
    label = f"{topic} ({subject})" if subject else topic
    title = f"{label} — {date.today().isoformat()}"

    chunks = _chunk(blocks)
    page = client.pages.create(
        parent={"page_id": page_id},
        properties={"title": [{"type": "text", "text": {"content": title}}]},
        children=chunks[0],
    )
    for chunk in chunks[1:]:
        client.blocks.children.append(block_id=page["id"], children=chunk)

    print(f"Published '{title}' to Notion.")
