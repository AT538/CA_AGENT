"""
Fetch UPSC question papers for the last 20 years:
- Prelims GS Paper 1 (Civil Services Aptitude Test / General Studies Paper 1)
- Mains GS Papers 1, 2, 3, 4

UPSC's official archive (https://upsc.gov.in/examinations/previous-question-papers)
restructures its page/PDF links periodically and is JS-rendered, so a fully
automated scraper is brittle. This script does a best-effort automated fetch
and falls back gracefully:

1. Tries to locate and download each year/paper's PDF automatically (only
   for entries you've populated in KNOWN_PDF_URLS below).
2. Anything it can't resolve, it logs clearly so you can manually drop the
   PDF into knowledge_base/pyqs/raw/ instead, using the naming pattern:
     <year>_prelims_gs1.pdf
     <year>_mains_gs1.pdf
     <year>_mains_gs2.pdf
     <year>_mains_gs3.pdf
     <year>_mains_gs4.pdf

Either way, parse_pyqs.py picks up whatever PDFs exist in pyqs/raw/ -
manual or automated makes no difference downstream.
"""

import httpx
from pathlib import Path
from datetime import datetime

RAW_DIR = Path(__file__).parent / "pyqs" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CURRENT_YEAR = datetime.now().year
YEARS = list(range(CURRENT_YEAR - 20, CURRENT_YEAR + 1))

PAPERS = ["prelims_gs1", "mains_gs1", "mains_gs2", "mains_gs3", "mains_gs4"]

# UPSC's PDF URL pattern changes year to year and isn't stable enough to
# hardcode reliably 20 years back. Populate this dict as you find working
# direct links (check https://upsc.gov.in/examinations/previous-question-papers).
# Key format: "<year>_<paper>", e.g. "2025_mains_gs2"
KNOWN_PDF_URLS = {
    # "2025_prelims_gs1": "https://upsc.gov.in/sites/default/files/CSP-GS1-2025.pdf",
    # "2025_mains_gs2": "https://upsc.gov.in/sites/default/files/CSM-GS2-2025.pdf",
}


def fetch_one(year: int, paper: str) -> bool:
    dest = RAW_DIR / f"{year}_{paper}.pdf"
    if dest.exists():
        return True  # already present, silent skip (log summary handles counts)

    key = f"{year}_{paper}"
    url = KNOWN_PDF_URLS.get(key)
    if not url:
        return False

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        print(f"[ok] downloaded {key}")
        return True
    except Exception as e:
        print(f"[error] {key}: {e}")
        return False


def main():
    print(f"Attempting to fetch Prelims GS1 + Mains GS1-4 for {YEARS[0]}-{YEARS[-1]}")
    print(f"That's up to {len(YEARS) * len(PAPERS)} PDFs across {len(YEARS)} years x {len(PAPERS)} papers.\n")

    missing = []
    already_present = 0
    fetched = 0

    for year in YEARS:
        for paper in PAPERS:
            dest = RAW_DIR / f"{year}_{paper}.pdf"
            if dest.exists():
                already_present += 1
                continue
            ok = fetch_one(year, paper)
            if ok:
                fetched += 1
            else:
                missing.append(f"{year}_{paper}")

    print(f"\nAlready present: {already_present}")
    print(f"Freshly fetched: {fetched}")
    print(f"Need manual download: {len(missing)}")

    if missing:
        print(f"\nGrab these from https://upsc.gov.in/examinations/previous-question-papers")
        print(f"and save into {RAW_DIR} using the exact filenames below:")
        for m in missing:
            print(f"  {m}.pdf")
        print("\nTip: prioritize the most recent 5-8 years first - PYQ patterns from "
              "the last decade are far more predictive of current exam style than "
              "very old papers, so partial coverage is still useful immediately.")


if __name__ == "__main__":
    main()
