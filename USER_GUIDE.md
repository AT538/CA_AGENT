# User Guide

Step-by-step: install, configure, run locally, host on GitHub, and maintain.
For *why* the system is built this way, see **ARCHITECTURE.md**.

---

## 1. One-time setup

```bash
cd upsc-current-affairs-agent
pip install -r requirements.txt
```

You'll also need, before your first real run:
- A free **Groq** or **Gemini** API key (for the relevance-judging step)
- A **Notion integration token** and a target Notion page

Get those now (§4 below has the details) so you're not blocked mid-setup.

---

## 2. Build the knowledge base (once)

This step feeds the syllabus + PYQs into a local searchable index. You only
redo this if you change the syllabus or add new PYQs later.

```bash
python knowledge_base/fetch_pyqs.py
```

This tries to auto-download 20 years of Prelims GS1 + Mains GS1-4 papers.
Since UPSC's official archive restructures its PDF links every year, most
years will print something like:

```
Grab these from https://upsc.gov.in/examinations/previous-question-papers
and save into knowledge_base/pyqs/raw/ using the exact filenames below:
  2023_mains_gs2.pdf
  2019_prelims_gs1.pdf
  ...
```

**What you need to do manually:** go to that UPSC page, download the PDF
for each year/paper, and save it into `knowledge_base/pyqs/raw/` using
*exactly* the filename shown (e.g. `2023_mains_gs2.pdf`). You don't have to
do all 20 years at once — start with the last 5-8 years; recent PYQs matter
more for exam-style prediction than very old ones, and the system works
fine with partial coverage.

Once you've dropped in whatever PDFs you have:

```bash
python knowledge_base/parse_pyqs.py             # PDFs -> pyqs.json
python knowledge_base/build_syllabus_index.py   # syllabus + pyqs -> embedding index
```

Open `knowledge_base/pyqs.json` afterward and skim a few entries — PDF text
extraction occasionally merges or splits a question awkwardly, especially
Mains questions with sub-parts like (a)/(b). Fix by hand if you spot issues.

---

## 3. How each source is actually pulled

| Category | Examples | Mechanism | Config section |
|---|---|---|---|
| Daily, has RSS | PIB, The Hindu, Indian Express, Down To Earth | `feedparser` reads the feed directly | `rss_sources` |
| Daily, no RSS | PRS Bill Track | `httpx` + `BeautifulSoup` scrape, respects `robots.txt` | `scrape_sources` |
| Monthly PDF, auto | Yojana, Kurukshetra, PRS Monthly Policy Review | scrapes the listing page for the latest PDF link, downloads it | `monthly_pdf_sources` (`auto_fetch: true`) |
| Monthly PDF, manual only | Vision IAS | **you** download and drop the PDF in | `monthly_pdf_sources` (`auto_fetch: false`) |
| Annual PDF, auto | Union Budget, Economic Survey | same as monthly, checked once a year | `annual_pdf_sources` |

Every PDF source (auto or manual) gets the same treatment once it's on disk:
text extracted, split into ~500-word chunks, and each chunk flows through
retrieval + judgment exactly like a daily news article.

**What you need to do manually, ongoing:**
- Drop **Vision IAS**'s monthly PDF into `knowledge_base/monthly_pdfs/manual/`
  each month, named `visionias_<YYYY-MM>.pdf`
- If an `auto_fetch: true` source's listing page ever changes layout and
  stops finding the PDF (you'll see a `[warn] no PDF link found` in the
  console), either fix the selector in `ingest/monthly_pdfs.py` or just drop
  that month's PDF into `knowledge_base/monthly_pdfs/manual/` as a fallback
  — both folders are read identically.

---

## 4. Configure sources and output

Edit `config.yaml`:

- **`rss_sources` / `scrape_sources`** — add or remove daily sources. For a
  new RSS feed, just add `{name, url}` — no code changes needed.
- **`monthly_pdf_sources` / `annual_pdf_sources`** — add `{name,
  listing_url, auto_fetch, notes}`. Set `auto_fetch: false` for anything
  behind a login (manual-only, same as Vision IAS).
- **`notion.database_or_page_id`** — the Notion page daily pages get
  created under.
- **`llm.provider` / `llm.model`** (+ `fallback_provider`/`fallback_model`)
  — Tier 1: the cheap/free model that judges every incoming item for
  relevance and produces the factual summary. Keep this on a genuinely free
  tier since it runs on high volume.
- **`llm.exam_angle`** — Tier 2: runs only on items Tier 1 already marked
  relevant (a much smaller set), producing probable questions, applicability,
  and the ready-to-cite answer example. Since volume here is low, this is
  the place to try a stronger model if Tier 1's exam-angle output ever
  feels bland — bump `llm.exam_angle.model` to a stronger free-tier option,
  or uncomment the Anthropic option in `config.yaml` (needs
  `ANTHROPIC_API_KEY`) for occasional paid-tier sharpness without touching
  Tier 1's cost.

### Getting your credentials

| Credential | How to get it |
|---|---|
| `GROQ_API_KEY` | console.groq.com → sign up (free) → API Keys → Create |
| `GEMINI_API_KEY` | aistudio.google.com → Get API Key (free tier) |
| `NOTION_TOKEN` | notion.so/my-integrations → New integration → copy the token, then open your target Notion page → "..." menu → Connect to → select your integration |

Get the Notion page ID from its URL — it's the long string of letters/numbers
right before any `?` in the page's URL.

Set these locally for testing (create a `.env` file, or export them in your
shell):
```bash
export GROQ_API_KEY=your_key_here
export NOTION_TOKEN=your_token_here
```

---

## 5. Test it locally

```bash
python main.py
```

You'll see, in order: daily RSS/scrape ingestion, the monthly/annual PDF
check, then each item printed as `[RELEVANT]` or `[skip]`, then confirmation
of the Notion page published. Open Notion — you should see a new page titled
`UPSC Current Affairs — YYYY-MM-DD` with a **Quick Summary** section and a
**Full Digest (with sources)** section underneath.

If nothing showed up as relevant, that's often fine on a quiet news day —
but if it happens every run, check:
- Is `knowledge_base/index/` actually built? (§2)
- Is your LLM API key valid and not rate-limited?
- Try lowering the bar by testing with `retrieval.top_k` raised slightly in `config.yaml`

---

## 6. Host it on GitHub (so it runs daily without your laptop)

If you haven't already:

```bash
cd upsc-current-affairs-agent
git init
git add .
git commit -m "Initial commit"
```

Create a new repository on GitHub (github.com → New repository — leave it
empty, no README/gitignore, since you already have one), then:

```bash
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git branch -M main
git push -u origin main
```

**Add your secrets** so the workflow can authenticate without them being in
the code: on GitHub, go to your repo → **Settings → Secrets and variables →
Actions → New repository secret**, and add each of:
- `GROQ_API_KEY`
- `GEMINI_API_KEY` (if you're using Gemini as primary or fallback)
- `NOTION_TOKEN`

That's it — `.github/workflows/daily.yml` is already in the repo. It'll run
automatically at 06:00 IST every day. To confirm it's wired up correctly
without waiting for tomorrow, go to your repo's **Actions** tab → select
"Daily UPSC Current Affairs Run" → **Run workflow** to trigger it manually.

Watch the run's logs the same way you watched the local `python main.py`
output — same print statements, same behavior.

---

## 7. Adding new items to the knowledge base later

### Adding a new syllabus topic
1. Open `knowledge_base/syllabus.json`
2. Add a new entry: `{"id": "...", "paper": "...", "topic": "...", "description": "..."}`
3. Re-run: `python knowledge_base/build_syllabus_index.py` (rebuilds the whole index — quick, since it's just the syllabus + PYQ set, not daily articles)
4. Commit the updated `syllabus.json` and `knowledge_base/index/`

### Adding new PYQ years
1. Get the PDF from https://upsc.gov.in/examinations/previous-question-papers
2. Save into `knowledge_base/pyqs/raw/` as `<year>_<paper>.pdf` (paper = `prelims_gs1` | `mains_gs1` | `mains_gs2` | `mains_gs3` | `mains_gs4`)
3. Re-run:
   ```bash
   python knowledge_base/parse_pyqs.py
   python knowledge_base/build_syllabus_index.py
   ```
4. Commit the updated `pyqs.json` and `knowledge_base/index/`

### Adding a brand-new daily source
1. If it has an RSS feed: add `{name, url}` under the right category in
   `config.yaml` → `rss_sources`. Done, no code changes.
2. If it doesn't: add an entry under `scrape_sources`, and check the output
   of a test run — the generic scraper in `ingest/scrapers.py` may need its
   CSS selector tightened for that specific site's layout.

### Adding a brand-new monthly/annual PDF source
1. Add an entry under `monthly_pdf_sources` or `annual_pdf_sources` in
   `config.yaml`, with `auto_fetch: true` if it's a public listing page, or
   `false` if it needs manual drop-in.
2. If `auto_fetch: true`, test a run and check whether
   `ingest/monthly_pdfs.py` finds the right PDF link — the generic
   "grab the first `.pdf` link on the page" logic may need a nudge for an
   unusual layout.

---

## 8. Ongoing maintenance checklist

- **Monthly**: drop the new Vision IAS PDF into `knowledge_base/monthly_pdfs/manual/`
- **Yearly**: run `fetch_pyqs.py` again for the newest year's papers once released
- **As needed**: if a scraper stops finding content (check console warnings),
  tighten its CSS selector in `ingest/scrapers.py` or `ingest/monthly_pdfs.py`
- **If a free-tier LLM changes its limits/pricing**: swap `llm.provider` in
  `config.yaml` — no code changes needed
