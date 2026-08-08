"""
Scrapers for sites without usable RSS feeds (config.yaml -> scrape_sources).

Kept deliberately simple and per-site: each site gets its own small function
because layouts differ enough that a generic scraper is more trouble than
it's worth. Add a new function here + a matching entry in config.yaml when
you add a new non-RSS source.

Always respects robots.txt and runs at most once/day per source - no
aggressive polling.
"""

import httpx
import yaml
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
HEADERS = {"User-Agent": "upsc-current-affairs-agent/0.1 (personal study tool)"}


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def robots_allow(url: str) -> bool:
    parsed = httpx.URL(url)
    robots_url = f"{parsed.scheme}://{parsed.host}/robots.txt"
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(HEADERS["User-Agent"], url)
    except Exception:
        # If robots.txt can't be read, default to cautious: allow, but log it.
        print(f"[warn] couldn't read robots.txt for {parsed.host}, proceeding cautiously")
        return True


def scrape_generic_links(url: str, source_name: str, link_selector: str = "a", max_items: int = 30) -> list[dict]:
    """
    Minimal generic fallback: grabs anchor tags matching a CSS selector.
    Works as a starting point - you'll likely want a site-specific selector
    (e.g. article headline links only, not nav links) once you see real output.

    max_items caps how many of the matched links are kept, taking the first
    N in document order. Listing pages are typically newest-first, and
    without this cap an unpaginated archive page (e.g. a bill tracker with
    years of history) gets re-scraped and re-judged as "current" every run.
    """
    if not robots_allow(url):
        print(f"[skip] robots.txt disallows {url}")
        return []

    resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    for link in soup.select(link_selector):
        if len(articles) >= max_items:
            break
        href = link.get("href", "")
        title = link.get_text(strip=True)
        if href and title and len(title) > 20:  # crude filter for real headlines
            articles.append({
                "url": href if href.startswith("http") else str(httpx.URL(url).join(href)),
                "title": title,
                "summary": "",
                "published": "",
                "source": source_name,
                "category": "magazine",
            })
    return articles


def fetch_all_scraped() -> list[dict]:
    config = load_config()
    all_articles = []

    for source in config.get("scrape_sources", []):
        print(f"Scraping: {source['name']} ({source['url']})")
        try:
            articles = scrape_generic_links(
                source["url"],
                source["name"],
                link_selector=source.get("link_selector", "a"),
                max_items=source.get("max_items", 30),
            )
            print(f"  -> found {len(articles)} candidate links")
            all_articles.extend(articles)
        except Exception as e:
            print(f"  [error] {source['name']}: {e}")

    return all_articles


if __name__ == "__main__":
    for a in fetch_all_scraped()[:5]:
        print(a["title"], "-", a["source"])
