"""
Ingestion for periodic PDF sources: Yojana, Kurukshetra, PRS Monthly Policy
Review, Vision IAS Monthly Magazine, Union Budget, Economic Survey.

These aren't daily articles - they're periodic compilations. This module:
1. For auto_fetch sources: best-effort scrape of the listing page to find
   the latest PDF link, download if not already seen this period.
2. For everything (auto or manual): reads whatever PDFs exist in
   knowledge_base/monthly_pdfs/{auto,manual}/, extracts text, and chunks
   each into article-sized pieces (~400-600 words) so they flow through
   the exact same retrieve -> judge -> publish pipeline as daily articles.

Manual fallback: sources that can't be reliably auto-scraped (Vision IAS,
often behind login) are simply skipped by auto-fetch - drop the PDF into
knowledge_base/monthly_pdfs/manual/ yourself and it's picked up identically.
"""

import re
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup

from ingest.pdf_utils import chunk_words, extract_pdf_text

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
PDF_DIR = Path(__file__).parent.parent / "knowledge_base" / "monthly_pdfs"
AUTO_DIR = PDF_DIR / "auto"
MANUAL_DIR = PDF_DIR / "manual"
PROCESSED_MARKER_DIR = PDF_DIR / ".processed"

HEADERS = {"User-Agent": "upsc-current-affairs-agent/0.1 (personal study tool)"}
CHUNK_WORD_COUNT = 500


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _ensure_dirs():
    AUTO_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_MARKER_DIR.mkdir(parents=True, exist_ok=True)


def _find_latest_pdf_link(listing_url: str) -> str | None:
    """Best-effort: grab the first PDF link on the listing page. Site
    layouts vary, so this is a starting point - tighten per-site if it
    picks up the wrong link."""
    try:
        resp = httpx.get(listing_url, headers=HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.lower().endswith(".pdf"):
                return href if href.startswith("http") else str(httpx.URL(listing_url).join(href))
    except Exception as e:
        print(f"  [error] couldn't scrape listing page {listing_url}: {e}")
    return None


def _safe_filename(name: str, url: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.lower()).strip("_")
    url_tail = re.sub(r"[^a-zA-Z0-9]+", "_", Path(url).stem)[-30:]
    return f"{slug}__{url_tail}.pdf"


def fetch_auto_sources():
    """Attempt to download the latest PDF for every auto_fetch source
    across monthly_pdf_sources and annual_pdf_sources."""
    _ensure_dirs()
    config = load_config()
    sources = config.get("monthly_pdf_sources", []) + config.get("annual_pdf_sources", [])

    for source in sources:
        if not source.get("auto_fetch"):
            print(f"[manual only] {source['name']} - drop PDFs into {MANUAL_DIR}")
            continue

        print(f"Checking: {source['name']} ({source['listing_url']})")
        pdf_url = _find_latest_pdf_link(source["listing_url"])
        if not pdf_url:
            print(f"  [warn] no PDF link found - may need a site-specific selector, "
                  f"or drop the PDF manually into {MANUAL_DIR}")
            continue

        dest = AUTO_DIR / _safe_filename(source["name"], pdf_url)
        if dest.exists():
            print(f"  [skip] already downloaded: {dest.name}")
            continue

        try:
            resp = httpx.get(pdf_url, headers=HEADERS, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            print(f"  [ok] downloaded -> {dest.name}")
        except Exception as e:
            print(f"  [error] download failed: {e}")


def _chunk_text(text: str, source_name: str, pdf_name: str) -> list[dict]:
    chunks = []
    for i, chunk_text in enumerate(chunk_words(text, CHUNK_WORD_COUNT)):
        chunks.append({
            "url": f"file://{pdf_name}#chunk{i}",
            "title": f"{source_name} — {pdf_name} (part {i + 1})",
            "summary": chunk_text,
            "published": "",
            "source": source_name,
            "category": "monthly_pdf",
        })
    return chunks


def _guess_source_name(pdf_path: Path) -> str:
    # filenames are "<slug>__<tail>.pdf" from _safe_filename, or free-form
    # for manually-dropped files - just use the stem as a readable label.
    return pdf_path.stem.split("__")[0].replace("_", " ").title()


def parse_all_pdfs() -> list[dict]:
    """Extract + chunk every PDF in auto/ and manual/ that hasn't been
    processed yet. Returns a list of article-shaped dicts ready for the
    same retrieve -> judge pipeline as ingest/feeds.py output."""
    _ensure_dirs()
    all_chunks = []

    for pdf_path in list(AUTO_DIR.glob("*.pdf")) + list(MANUAL_DIR.glob("*.pdf")):
        marker = PROCESSED_MARKER_DIR / f"{pdf_path.name}.done"
        if marker.exists():
            continue  # already chunked in a previous run

        print(f"Parsing monthly/annual PDF: {pdf_path.name}")
        try:
            full_text = extract_pdf_text(pdf_path)
        except Exception as e:
            print(f"  [error] couldn't extract text: {e}")
            continue

        source_name = _guess_source_name(pdf_path)
        chunks = _chunk_text(full_text, source_name, pdf_path.name)
        print(f"  -> {len(chunks)} chunks")
        all_chunks.extend(chunks)
        marker.touch()

    return all_chunks


if __name__ == "__main__":
    fetch_auto_sources()
    for c in parse_all_pdfs()[:3]:
        print(c["title"])
