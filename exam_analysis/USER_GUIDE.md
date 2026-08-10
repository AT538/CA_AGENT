# PYQ Exam Analysis — User Guide

Step-by-step: prerequisites, configure, run locally, run on GitHub, and
read the output. For *why* it's built this way, see **ARCHITECTURE.md**.

---

## 1. Prerequisite: question papers must exist

This tool reads `knowledge_base/pyqs.json` — the same file the main
pipeline's knowledge base uses. If you've already run the main repo's setup
(../USER_GUIDE.md §2), you're done with this step. If not:

```bash
python knowledge_base/fetch_pyqs.py    # best-effort auto-download
python knowledge_base/parse_pyqs.py    # PDFs in knowledge_base/pyqs/raw/ -> pyqs.json
```

`fetch_pyqs.py` only auto-downloads years/papers you've populated in its
`KNOWN_PDF_URLS` dict — most years, it'll print a list of files to grab
manually from
[upsc.gov.in/examinations/previous-question-papers](https://upsc.gov.in/examinations/previous-question-papers)
and drop into `knowledge_base/pyqs/raw/` as `<year>_<paper>.pdf`
(paper = `prelims_gs1` | `mains_gs1` | `mains_gs2` | `mains_gs3` | `mains_gs4`).
You don't need all 20 years at once — start with the last 5-8; recent PYQs
predict current exam style far better than old ones, and this tool works
fine with partial coverage.

Running `exam_analysis/run.py` without `pyqs.json` in place fails
immediately with these same instructions, rather than doing nothing silently.

---

## 2. Configure

Edit `config.yaml`:

- **`exam_analysis.analysis_llm`** — the model that analyzes each question
  (runs once per question — moderate volume: ~20 calls for a Mains paper,
  ~100 for Prelims GS1). Defaults to the same free-tier chain as the daily
  pipeline's Tier 1.
- **`exam_analysis.prediction_llm`** — the model that turns the accumulated
  cache into a topic/question prediction (runs once per invocation,
  regardless of cache size). Defaults to the same free-tier chain as the
  daily pipeline's Tier 2.
- **`notion.exam_analysis_page_id`** — a Notion page shared with your
  integration, **different from** `notion.database_or_page_id` (the daily
  digest's page) — keep the two output streams separate. Leave empty to
  skip Notion publishing; results still get cached locally either way.

If you've already set up `GROQ_API_KEY`/`GEMINI_API_KEY`/`NOTION_TOKEN` for
the main pipeline (../USER_GUIDE.md §4), no new credentials are needed —
this tool reuses them.

---

## 3. Run it locally

```bash
# One paper, one year
python -m exam_analysis.run --year 2023 --paper mains_gs2

# Every paper for a given year
python -m exam_analysis.run --year 2023 --paper all

# Everything in pyqs.json - can be a lot of LLM calls at once, see §6
python -m exam_analysis.run --all

# Just refresh the prediction from what's already cached - no new analysis
python -m exam_analysis.run --predict-only

# Predict for a different target year (default is 2027)
python -m exam_analysis.run --all --target-year 2028

# Cap new LLM calls this invocation (quota safety / testing)
python -m exam_analysis.run --year 2023 --paper mains_gs2 --limit 5

# Re-analyze a paper even though it's already cached
python -m exam_analysis.run --year 2023 --paper mains_gs2 --force
```

You'll see each question printed as it's analyzed
(`[ok] 2023 mains_gs2 -> ['Governance, Transparency and Accountability']`),
then a summary of how many were newly analyzed vs. already cached, then
confirmation of the Notion page published.

If a question fails analysis (all LLM providers down that moment), it's
printed as `[failed]` and simply isn't cached — it'll be retried
automatically the next time you run that paper, without needing `--force`.

---

## 4. Run it on GitHub (on-demand, not scheduled)

Unlike the daily pipeline, this workflow has **no cron trigger** — it only
runs when you tell it to:

- **From the Actions tab**: your repo → **Actions** → "PYQ Exam Analysis
  (on-demand)" → **Run workflow** → fill in year/paper/target year/etc.
- **From the CLI**: `gh workflow run exam_analysis.yml -f paper=mains_gs2 -f year=2023`

Uses the same repo secrets as the daily workflow
(`GROQ_API_KEY`/`GEMINI_API_KEY`/`OPENROUTER_API_KEY`/`NOTION_TOKEN`, or
their `_KEYS` rotation variants) — nothing new to add if the daily
workflow is already set up.

The workflow commits `exam_analysis/analyzed_questions.json` back to the
repo after each run, same as `daily.yml` does for `data/articles.db` —
GitHub-hosted runners don't persist disk between runs, so without this,
every run would start from an empty cache and re-spend quota re-analyzing
questions you'd already covered.

---

## 5. Reading the output

Each run creates **one new Notion page**
(`PYQ Analysis — <year> <paper> — YYYY-MM-DD`, or
`PYQ Analysis — prediction refresh — YYYY-MM-DD` for `--predict-only`),
under `notion.exam_analysis_page_id`, with two sections:

1. **Potential {target year} Topics & Questions** — high-probability
   topics, probable questions, current events to watch, and a rationale —
   built from *everything* analyzed so far, not just this run.
2. **Question Analysis** — this run's own per-question breakdown: syllabus
   topic(s), trigger (syllabus/current-event/both), and why it was likely asked.

If nothing shows up in Notion, check:
- Is `notion.exam_analysis_page_id` actually set in `config.yaml`? (a
  `[warn]` prints and the run continues without publishing if it's empty)
- Did every LLM provider fail that run? Check for `[error]` lines in the
  console output.

---

## 6. Cost / quota — using this without blowing your free-tier limits

- Each **new** question analyzed costs one LLM call. Already-cached
  questions cost nothing — this is why `--force` is opt-in, not the default.
- `--all` across many years can mean hundreds of calls in one run. If
  you're on free-tier quotas, spread it out: run a few papers at a time, or
  use `--limit` to cap how many new calls happen in one invocation — the
  rest just get picked up on your next run.
- The prediction step is one call per invocation, cheap regardless of
  cache size — running `--predict-only` repeatedly (e.g. after adding a
  new syllabus topic) is effectively free.

---

## 7. Ongoing maintenance checklist

- **When a new year's papers are released**: run the main repo's
  `fetch_pyqs.py`/`parse_pyqs.py` for the new year, then
  `python -m exam_analysis.run --year <new-year> --paper all`.
- **If you want a fresher/different prediction**: `--predict-only`, or
  `--target-year` for a different year — no need to re-analyze anything.
- **If a question's analysis looks wrong** (e.g. a clearly mis-tagged
  syllabus topic): re-run that specific paper with `--force` — useful after
  tweaking the prompt in `analyzer.py` or improving `syllabus.json`.
