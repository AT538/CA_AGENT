"""
RSS ingestion - pulls new articles from all rss_sources in config.yaml.
"""

import feedparser
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def fetch_all_rss() -> list[dict]:
    config = load_config()
    articles = []

    for category, sources in config.get("rss_sources", {}).items():
        for source in sources:
            print(f"Fetching RSS: {source['name']}")
            feed = feedparser.parse(source["url"])
            if feed.bozo:
                print(f"  [warn] feed parse issue: {feed.bozo_exception}")

            for entry in feed.entries:
                articles.append({
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                    "source": source["name"],
                    "category": category,
                })
            print(f"  -> {len(feed.entries)} entries"
                  f"{' (status ' + str(feed.get('status')) + ')' if feed.get('status') and feed.get('status') != 200 else ''}")

    print(f"Fetched {len(articles)} articles total from RSS sources")
    return articles


if __name__ == "__main__":
    for a in fetch_all_rss()[:5]:
        print(a["title"], "-", a["source"])
