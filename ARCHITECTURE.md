# UPSC Current Affairs Agent — Architecture

This document explains *how the system works and why it's built this way* —
useful if you're new to agent-building and want to understand the design,
not just run it. For "how do I actually run this," see **USER_GUIDE.md**.

---

## Goal

Every day (and whenever a new monthly/annual publication drops), automatically
read a fixed set of UPSC sources, decide which items are genuinely relevant
using the full UPSC syllabus and 20 years of previous question papers as the
relevance backbone, and publish a new Notion page every day — condensed into
plain language, tagged back to the syllabus, with probable exam questions and
a ready-to-cite example for Mains/Essay answers.

This is what's called a **RAG pipeline** (Retrieval-Augmented Generation) —
a very common agent pattern. The core idea: instead of asking an LLM to
"know" the entire UPSC syllabus and 20 years of PYQs from memory (expensive,
unreliable, and wasteful for every single article), you store that knowledge
separately, **retrieve** only the most relevant pieces of it for each
article, and hand just that slice to the LLM to make its final judgment.
This is the same pattern behind most "chat with your documents" tools.

Runs unattended on GitHub Actions (free tier). No local machine dependency.

---

## 1. High-level flow

```
 INGEST (daily RSS+scrape, plus monthly/annual PDFs as released)
   --> DEDUPE (vs seen-items DB)
   --> FILTER/JUDGE (embed -> retrieve syllabus/PYQ context -> LLM judge)
   --> OUTPUT (new Notion page per day)

 KNOWLEDGE BASE (built once): full syllabus (Prelims+Mains+Ethics+Essay)
 + 20yr Prelims & Mains GS1-4 PYQs -> embedded -> feeds the retrieve step
```

Orchestrated by `main.py`, triggered daily by a GitHub Actions cron workflow.

---

## 2. Sources

### 2.1 Daily / near-daily (RSS + light scraping)
- **PIB** (Press Information Bureau) — RSS, all-ministry release feed
- **The Hindu** — Editorial + National — RSS
- **Indian Express** — "Explained" section — RSS
- **Down To Earth** — environment-focused — RSS
- **PRS India — Bill Track** — legislative summaries — scraped (no RSS)

### 2.2 Monthly compilations (PDF, handled separately from daily articles)
- **Yojana** and **Kurukshetra** (Publications Division) — monthly issues
- **PRS Monthly Policy Review** — best single source for Parliament/policy tracking
- **Vision IAS Monthly Current Affairs Magazine** — often behind login/subscription; manual drop-in only

### 2.3 Annual (PDF, checked once a year around the Union Budget in February)
- **Union Budget** documents (indiabudget.gov.in)
- **Economic Survey** (tabled the day before the Budget)

> Why three categories instead of one list? A daily newspaper article and an
> annual 400-page Economic Survey need fundamentally different handling —
> one is a single small item, the other needs to be split into chunks
> before it can be judged for relevance. Keeping them as separate config
> sections keeps that difference explicit rather than papered over.

---

## 3. Knowledge base (syllabus + PYQs)

This is the relevance backbone — the "retrieval" side of RAG. Built **once**,
reused every run.

### 3.1 Syllabus — Prelims + Mains + Ethics + Essay
`knowledge_base/syllabus.json` covers the entire syllabus as ~40 separate
sub-topic entries (`id`, `paper`, `topic`, `description`) — not one giant
blob of text. This granularity matters: embedding search works by comparing
*meaning similarity*, and a giant blob dilutes the signal for any single
topic. One entry per sub-topic is what makes retrieval precise.

### 3.2 Previous 20 years' question papers — Prelims GS1 + Mains GS1-4
Parsed into `knowledge_base/pyqs.json`, one entry per question, tagged with
year, paper, and marks (for Mains). This gives the LLM concrete evidence of
*how UPSC actually phrases and weights questions* on a topic, not just the
syllabus's abstract description of it.

### 3.3 Embedding + indexing
A local embedding model (`sentence-transformers`, `bge-small-en-v1.5`)
converts every syllabus entry and every PYQ into a vector — a list of
numbers representing its meaning. These are stored in a local Chroma
database. At judgment time, the incoming article is embedded the same way,
and the database finds the syllabus/PYQ entries whose vectors are closest
(most similar in meaning) — that's the "retrieval" step.

---

## 4. Ingestion

**Daily sources** (`ingest/feeds.py`, `ingest/scrapers.py`): RSS parsed via
`feedparser` wherever available; non-RSS sites scraped via `httpx` +
`BeautifulSoup`, respecting `robots.txt`.

**Monthly/annual PDF sources** (`ingest/monthly_pdfs.py`): for auto-fetch
sources, a best-effort scrape of the listing page finds the latest PDF.
Every PDF (auto or manually dropped) gets text-extracted and **chunked**
into ~500-word pieces, so a 40-page issue becomes ~15-20 pieces that flow
through the *same* pipeline as a daily article — no separate logic needed
downstream.

Everything is hashed and checked against a seen-items store, so re-runs
never duplicate work.

---

## 5. Filtering / relevance judgment (the two-stage retrieval core, plus a two-tier LLM design)

**Stage 1 — Retrieval (local, free):** embed the incoming item, find the
top-k most similar syllabus/PYQ entries.

**Stage 2 — LLM judgment, split into two tiers by cost/volume:**

- **Tier 1 (`judge_relevance`)** runs on *every* incoming item — every
  article, every PDF chunk. This has to stay cheap, so it only asks for the
  fields that are closer to classification/extraction (a task small/free
  models handle reliably): `relevant`, `gs_paper`, `topics`, `summary`,
  `relevance_note`.
- **Tier 2 (`generate_exam_angle`)** runs *only* on items Tier 1 already
  marked relevant — a much smaller set, often a small fraction of daily
  volume. It handles the harder, more generative fields: `probable_questions`,
  `applicability`, `answer_example`. Because volume here is low, this tier
  can point at a stronger model (a better free-tier option, or even an
  occasional paid call) without meaningfully affecting overall cost.

```json
// Tier 1 output
{
  "relevant": true/false,
  "gs_paper": "GS1 / GS2 / GS3 / GS4 / Prelims-only / Essay",
  "topics": ["Indian Polity", "..."],
  "summary": "3-5 line plain-language summary of the actual content",
  "relevance_note": "why this maps to the syllabus topic or a PYQ pattern"
}

// Tier 2 output (only computed for relevant items)
{
  "probable_questions": ["1-3 realistic exam-style questions"],
  "applicability": ["e.g. 'GS2 Mains (Governance)', 'GS4 Ethics case study'"],
  "answer_example": "a ready-to-cite example drawn from this article's specific facts"
}
```

**Why split the LLM call itself, not just the fields?** This is a general
cost-control pattern worth knowing: when a pipeline has a "filter everything
→ enrich the survivors" shape, run the expensive/harder work only on the
survivors. Volume drops sharply between the two stages (most articles
aren't relevant), so the second, harder call can afford a better model
without the overall bill changing much. This is different from just
choosing one model for everything — it's tiering the *work* by cost and
matching the *model* to each tier separately.

**Why is this design what makes free-tier models viable at all?**
Without retrieval, you'd have to either paste the entire syllabus + PYQ set
into every call, or trust the LLM to "know" UPSC relevance from training
data with no traceability. Retrieval narrows the field first, and now the
two-tier split narrows the *expensive* reasoning down further to just the
items that earned it.

---

## 6. Output

`output/notion_writer.py` creates a **new Notion page every day**
(`UPSC Current Affairs — YYYY-MM-DD`), never appended to a prior day.

1. **Quick Summary** — grouped by GS paper → syllabus topic (syllabus
   description shown as the simple cue). Each item: its factual `summary`,
   then a collapsed **"Exam angle" toggle** with the `answer_example`,
   `applicability`, and `probable_questions` — one click away.
2. **Full Digest (with sources)** — title + link back to the original,
   same summary, explicit `relevance_note`, same Exam angle toggle.

---

## 7. Model choice

The judging step is **two-tiered** (see §5): Tier 1 (relevance + summary)
runs on every item and stays on a free-tier model by design — Groq/Gemini/
OpenRouter. Tier 2 (exam angle: probable questions, applicability, answer
example) runs only on the relevant subset, so it's configured separately
(`config.yaml` → `llm.exam_angle`) and can point at a stronger model —
still free-tier by default, but with an optional paid escape hatch (an
Anthropic provider function is included, gated behind `ANTHROPIC_API_KEY`)
for occasional sharper output, since low volume keeps that cheap even on a
paid model.

Both tiers route through the same provider-agnostic `_call_with_fallback`
logic in `filter/judge.py` — swappable through config alone. Embeddings are
always local (`sentence-transformers`) — zero cost, zero dependency on any
API being up, since that step runs on every single article regardless of tier.

---

## 8. Scheduling & infra

GitHub Actions cron workflow, once a day, no server to maintain, survives
your laptop being off. This is a common "serverless cron" pattern for small
personal automation — free, and the compute only exists for the ~1-2 minutes
the job actually runs.

---

## 9. Persistence

| What | Where | Why |
|---|---|---|
| Seen-items (dedupe) | SQLite (`data/articles.db`), committed back each run | Needs to persist across throwaway CI runs |
| Syllabus/PYQ vector index | Committed to repo (`knowledge_base/index/`) | Built once, rarely changes |
| Downloaded PDFs | `knowledge_base/monthly_pdfs/{auto,manual}/` — gitignored | Re-downloadable; only extracted chunks matter |
| Daily digest | Notion | Permanent, readable archive |

---

## 10. Repo structure

```
upsc-current-affairs-agent/
  ARCHITECTURE.md    (this file)
  USER_GUIDE.md       how to run it
  SKILL.md            maintenance/extension reference for an AI assistant
  README.md
  config.yaml          sources, Notion id, LLM provider - the main dial-board
  requirements.txt
  main.py              orchestrates each run
  ingest/
    feeds.py            RSS ingestion
    scrapers.py          non-RSS daily site scraping
    monthly_pdfs.py       Yojana/Kurukshetra/PRS MPR/Vision IAS/Budget/Econ Survey
    dedupe.py             seen-items check against DB
  knowledge_base/
    syllabus.json          full Prelims + Mains GS1-4 + Ethics + Essay
    pyqs.json                parsed 20yr Prelims + Mains PYQs
    pyqs/raw/                 dropped PYQ PDFs (auto or manual)
    monthly_pdfs/auto/         auto-downloaded monthly/annual PDFs
    monthly_pdfs/manual/        manually dropped (e.g. Vision IAS)
    fetch_pyqs.py                20yr Prelims+Mains PYQ fetcher
    parse_pyqs.py                 PDFs -> pyqs.json
    build_syllabus_index.py        syllabus + pyqs -> embedding index
    index/                          committed Chroma index
  filter/
    retrieve.py           embedding similarity search
    judge.py                LLM relevance judgment (model-swappable)
  output/
    notion_writer.py        new page/day, Quick Summary + Full Digest
  data/
    articles.db              seen-items / dedupe store
  .github/workflows/
    daily.yml                  cron trigger
```

---

## 11. Design decisions & tradeoffs worth understanding

- **Chroma index committed to git, not hosted**: simplest possible setup —
  no external service, no extra credentials. Tradeoff: the index is a
  binary blob, so git diffs on it are meaningless, and it'll grow as you add
  PYQs. Fine at this scale (a few thousand chunks); a hosted vector DB
  (Qdrant Cloud free tier) would be the next step if it ever gets unwieldy.
- **SQLite committed back to the repo for dedupe, not a hosted DB**: same
  reasoning — zero external dependency, but every run adds a commit, and
  large tables bloat repo history over time. A hosted SQLite (Turso) or
  Postgres (Supabase) free tier avoids that, at the cost of one more secret
  to manage.
- **Free-tier LLM for judgment, not a frontier model**: because retrieval
  already narrows the task to "confirm and annotate," not "reason from
  scratch." This is a general lesson: pipeline design (good retrieval) often
  matters more than model size for narrowly-scoped classification tasks.
- **Two-tier LLM calls, not one call per item**: the harder, more generative
  fields (probable questions, answer examples) only run on the subset of
  items already confirmed relevant. This is a cost-control pattern worth
  reusing elsewhere: when a pipeline filters-then-enriches, spend the
  expensive step's budget only on survivors, not everything that comes in.
- **PDF chunking is fixed-size (500 words), not section-aware**: simplest
  approach that works reasonably well. It can occasionally split a thought
  mid-paragraph. Section-aware chunking (splitting on headers) would be more
  precise but needs per-source logic since PDF layouts vary.

---

## 12. Possible areas of improvement

Roughly in order of "cheapest to try first":

1. **Auto-tag PYQs with topics.** Right now `pyqs.json` entries have an
   empty `topics` list unless you fill them in by hand. You could run each
   parsed question through the LLM once (a one-time batch job, not part of
   the daily pipeline) to auto-tag it against `syllabus.json`, making
   retrieval even sharper.
2. **A small evaluation set.** Hand-label ~20-30 articles as
   relevant/irrelevant once, and write a tiny script that runs them through
   the pipeline and reports accuracy. This turns "does the judge prompt
   work well" from a vague feeling into a number you can track when you
   tweak the prompt or switch models.
3. **Feedback loop from Notion back into the pipeline.** If you mark items
   in Notion as "actually used this" vs "not useful," that signal could
   (eventually) refine the judge prompt or retrieval weighting — a genuine
   personalization loop, though non-trivial to wire up.
4. **Section-aware PDF chunking** for Yojana/Kurukshetra/Vision IAS —
   splitting on article headers instead of fixed word-counts would keep
   each chunk as one coherent piece rather than occasionally cutting mid-thought.
5. **Hosted dedupe + vector DB** (Turso + Qdrant Cloud, both have free
   tiers) once the git-committed approach starts to feel heavy — cleaner
   long-term, small setup cost now.
6. **Retry/backoff on scrapers and LLM calls.** Currently a failed fetch or
   API call is just logged and skipped for that item. Adding a retry with
   backoff would reduce the odds of losing a genuinely relevant article to
   a transient network blip.
7. **Playwright for JS-heavy sites** (Vision IAS's listing page, if it's
   ever worth automating despite the login wall) — heavier than
   `httpx`+`BeautifulSoup` but handles rendered content the current
   scraper can't see.
8. **Cost/quality monitoring** if you ever scale up the LLM tier — logging
   which provider/model handled each judgment makes it easy to compare
   quality later without re-running everything.

None of these are required to have a working system — the current design
is deliberately the simplest version that actually works end-to-end. Treat
this list as a backlog, not a checklist.
