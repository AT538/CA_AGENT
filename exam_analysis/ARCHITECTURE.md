# PYQ Exam Analysis — Architecture

This document explains *how this subsystem works and why* — for "how do I
actually run this," see **USER_GUIDE.md**. It assumes you've read the main
repo's **../ARCHITECTURE.md** first; this doc only covers what's different
here, and reuses that doc's vocabulary (retrieval, tiers, fallback chain)
without re-explaining it.

---

## Goal

The daily current-affairs pipeline (../main.py) only looks *forward* — it
turns today's news into exam-relevant material. This subsystem looks
*backward*: given 20 years of actual UPSC question papers, explain **why
each question was asked** (a recurring static-syllabus theme? a specific
current event at the time? both?), then use the accumulated pattern across
however many papers you've analyzed to predict **what's likely to be asked
in a future year** (2027 by default).

Unlike the daily pipeline, this is **on-demand, not scheduled** — you run
it against one paper, a handful, or everything, whenever you want, and the
results accumulate in a local cache across runs.

---

## 1. High-level flow

```
 knowledge_base/pyqs.json  (year, paper, question, marks — from the main
                             repo's existing fetch_pyqs.py + parse_pyqs.py,
                             reused as-is, not duplicated here)
   --> SELECT   (CLI: --year/--paper/--all, filtered against the cache
                 so already-analyzed questions are skipped)
   --> ANALYZE  (embed question --> retrieve syllabus/PYQ context --> LLM:
                 syllabus topic? syllabus-driven or current-event-driven?)
   --> CACHE    (exam_analysis/analyzed_questions.json, committed to git —
                 accumulates across every run you've ever done)
   --> PREDICT  (frequency-analyze the FULL cache, weighted toward recent
                 years --> LLM: likely topics/questions for the target year)
   --> PUBLISH  (one new Notion page per run: this run's analysis +
                 the refreshed prediction)
```

Orchestrated by `exam_analysis/run.py`, triggered manually — either
locally or via a `workflow_dispatch` GitHub Actions workflow (never a
cron schedule, unlike the daily pipeline).

---

## 2. Source data: previous-year question papers

This subsystem does **not** re-implement PYQ fetching/parsing — it reads
`knowledge_base/pyqs.json`, the same file the main pipeline's
`knowledge_base/fetch_pyqs.py` + `parse_pyqs.py` already produce (one entry
per question: `year`, `paper`, `question`, `marks`, `topics`). If that file
doesn't exist yet, `run.py` fails fast with instructions rather than
silently doing nothing — see USER_GUIDE.md §1.

**Why not build a separate ingestion path?** The main repo already has a
working PYQ pipeline that this exact use case needs verbatim. Duplicating
it would mean two sources of truth for the same PDFs drifting out of sync.

---

## 3. Analysis (per question)

Each question goes through the same two-stage retrieval pattern the daily
pipeline uses:

**Stage 1 — Retrieval (local, free, reused as-is):**
`filter/retrieve.py`'s `retrieve_context()` — the *exact same function and
embedding index* the daily pipeline uses — embeds the question text and
finds the closest syllabus/PYQ chunks. No separate index, no separate
embedding model.

**Stage 2 — LLM judgment** (`exam_analysis/analyzer.py`):

```json
{
  "syllabus_topics": ["the specific syllabus topic(s) this maps to"],
  "trigger": "syllabus | current_event | both",
  "trigger_note": "why - static theme, or a specific event around that year",
  "why_asked": "the underlying exam-setting logic"
}
```

**The syllabus side is grounded; the current-event side isn't — this is
deliberate and worth understanding.** Syllabus linkage comes from the local
embedding index, the same traceable evidence the daily pipeline relies on.
But there's no local database of *past* years' news to check a question
against — the daily pipeline only accumulates news *going forward* from
whenever you started running it. So for "was this asked because of a
current event," the LLM is answering from its own training knowledge, with
no retrieval backing it. `trigger_note` should be read as a plausible
hypothesis, not a verified citation. (A future improvement, if this
matters to you, is noted in §12.)

---

## 4. Prediction (aggregated, across the whole cache)

`exam_analysis/predictor.py`'s `build_prediction()` runs once per
invocation, over **every** question analyzed so far (not just the current
run's selection) — that's the point of caching results across runs instead
of throwing them away.

It doesn't hand the LLM the raw question text (that would grow unboundedly
expensive as the cache grows). Instead it computes:
- a frequency count of `syllabus_topics` across all analyzed years
- the same, restricted to the last 8 years (matching the main repo's own
  guidance that recent PYQs predict current exam style better than old ones)
- a short list of notable current-event-triggered questions, as concrete
  examples of the pattern

...and asks one LLM call to turn those signals into:

```json
{
  "high_probability_topics": ["..."],
  "probable_questions": ["..."],
  "watch_current_events": ["..."],
  "rationale": "..."
}
```

**Why this shape, not a raw LLM guess?** Same reasoning as the daily
pipeline's retrieval step: don't ask the model to "know" the pattern from
scratch on every call — hand it the actual computed evidence (frequency
counts, real examples) and let it reason over that. This also keeps the
prediction call's cost roughly **constant** regardless of cache size — only
the analysis step's cost scales with how many questions you've processed.

---

## 5. Output

`exam_analysis/notion_writer.py` creates **one new Notion page per
invocation** (unlike the daily pipeline's one-page-per-day — this tool has
no daily cadence, so "one page per run" is the natural unit). Each page has
two sections:

1. **Prediction** — high-probability topics, probable questions, current
   events to watch, rationale — built from the *entire* cache.
2. **This run's question analysis** — syllabus topic, trigger, why-asked,
   per question you just analyzed (empty if you used `--predict-only`).

Written to a **separate** Notion page from the daily digest
(`config.yaml` → `notion.exam_analysis_page_id`) so the two don't mix —
one's a daily current-affairs read, the other's an occasional trend report.

---

## 6. Model choice & provider fallback

Reuses `filter/llm_client.py` verbatim — the same Groq/Gemini/OpenRouter/
Ollama/Anthropic registry, key-rotation, and 3-way fallback chain
(`provider → fallback_provider → fallback_provider2`) the daily pipeline's
`filter/judge.py` uses. This subsystem just points two more "tier configs"
at it, via `config.yaml` → `exam_analysis.analysis_llm` and
`exam_analysis.prediction_llm`.

**Why extract `llm_client.py` instead of importing from `judge.py`
directly?** `judge.py`'s provider functions were originally private
(underscore-prefixed) implementation details of the daily pipeline. Rather
than reaching into another module's internals, the shared logic was pulled
into its own module that both import from — one place to add a provider or
fix a rotation bug, used by two independent call sites.

`analysis_llm` runs once per question (moderate volume — a Mains paper is
~20 questions, Prelims GS1 is ~100). `prediction_llm` runs once per
invocation regardless of cache size. Both default to the same free-tier
providers as the daily pipeline.

---

## 7. Caching & idempotency

`exam_analysis/cache.py` — a flat JSON file
(`exam_analysis/analyzed_questions.json`), keyed by
`"<year>_<paper>_<index-within-that-paper>"`. Re-running an already-analyzed
paper is free (skipped unless `--force`); this is what makes "run it for
each question paper when I want" cheap to do repeatedly instead of
re-spending quota every time.

**Why JSON, not SQLite (unlike the daily pipeline's `data/articles.db`)?**
Volume here is fundamentally different — thousands of questions at most
across 20 years x 5 papers, not a daily-growing stream. A flat JSON file is
easy to open and read directly, diff-friendly enough to spot-check, and
doesn't need SQL for a dataset this size. SQLite would be the right call if
this ever needed range queries or grew far larger.

---

## 8. Scheduling & infra

**On-demand only — no cron.** Unlike the daily pipeline, there's no "every
day" cadence that makes sense here; you analyze a paper when you want to,
not on a schedule. Two ways to run it:
- **Locally**: `python -m exam_analysis.run ...` (see USER_GUIDE.md)
- **GitHub Actions**: `.github/workflows/exam_analysis.yml`, a
  `workflow_dispatch` workflow — triggered manually from the Actions tab or
  `gh workflow run`, never on a timer.

---

## 9. Persistence

| What | Where | Why |
|---|---|---|
| Analyzed-question cache | `exam_analysis/analyzed_questions.json`, committed to git | Same reasoning as `data/articles.db`: GitHub Actions runners are ephemeral, so results must persist via git or every CI run starts from zero |
| Question papers | `knowledge_base/pyqs.json` (main repo, not duplicated) | Already the single source of truth |
| Syllabus/PYQ vector index | `knowledge_base/index/` (main repo, reused) | Same index the daily pipeline builds — no second index |
| Prediction/analysis output | Notion | Permanent, readable archive — same as the daily digest |

---

## 10. Repo structure

```
exam_analysis/
  README.md              (this subsystem's index - links to the 3 docs below)
  ARCHITECTURE.md         (this file)
  USER_GUIDE.md            how to run it
  SKILL.md                  maintenance/extension reference for an AI assistant
  __init__.py
  cache.py                  local JSON cache, keyed by <year>_<paper>_<index>
  analyzer.py                per-question "why was this asked" LLM call
  predictor.py                 aggregates the full cache into a future-year prediction
  notion_writer.py               publishes one page per run
  run.py                          CLI entrypoint (--year/--paper/--all/--predict-only/...)
  analyzed_questions.json          the cache itself (committed, grows over time)

filter/
  llm_client.py           shared provider registry + fallback chain (also used by judge.py)
  retrieve.py               embedding similarity search (also used by the daily pipeline)

knowledge_base/
  pyqs.json                reused as-is (this subsystem's input, not its output)

.github/workflows/
  exam_analysis.yml       workflow_dispatch - manual trigger only, commits the cache back
```

---

## 11. Design decisions & tradeoffs worth understanding

- **Shared `filter/llm_client.py` instead of a second provider registry**:
  avoids two divergent copies of key-rotation/fallback logic. Tradeoff:
  this subsystem now depends on `filter/`, so a breaking change there
  affects both the daily pipeline and this tool — acceptable, since they
  should genuinely stay in sync (e.g. adding a new LLM provider should work
  for both without extra effort).
- **Prediction reads the full cache every time, not just the current run's
  selection**: the whole point is a cumulative picture across everything
  you've ever analyzed. The cost is flat (frequency summary, not raw text),
  so there's no reason to scope it down.
- **No verification/grounding for "current event" triggers**: as discussed
  in §3, this is a real limitation, not an oversight — building a database
  of *past* years' news was out of scope for what the daily pipeline
  already provides (which only looks forward). Treat `trigger_note` as a
  hypothesis to sanity-check, not a fact.
- **On-demand, not scheduled**: deliberately no cron trigger, unlike the
  daily pipeline — analyzing 20 years of PYQs isn't a "check every day"
  task, and running it automatically would just burn free-tier quota on a
  fixed cache that barely changes.

---

## 12. Possible areas of improvement

1. **Auto-verify current-event triggers with a search step.** If
   `trigger_note`'s "current_event" claims need to be more than a plausible
   guess, a web-search-grounded verification pass (per question, or just
   for the ones flagged `current_event`) would close the gap noted in §3 —
   at the cost of another API dependency and more calls.
2. **Auto-tag `pyqs.json`'s empty `topics` field** using this subsystem's
   own `syllabus_topics` output — a natural byproduct of running analysis
   that could feed back into the main pipeline's retrieval quality (see the
   main repo's own ARCHITECTURE.md §12, which flags this same idea from the
   other direction).
3. **Per-paper or per-topic prediction**, not just one blended prediction
   across every paper — e.g. "likely GS2 Mains topics" separate from
   "likely Prelims topics" might be more directly useful than one
   combined list.
4. **A confidence/frequency score surfaced per predicted topic**, instead
   of just an LLM-authored ranked list — the underlying frequency counts
   already exist in `predictor.py`, they're just not exposed in the output
   today.
5. **SQLite if the cache ever outgrows JSON** — unlikely at PYQ-paper
   scale (thousands of questions, not millions), but the same tradeoff
   discussion as the main repo's dedupe store applies if this ever changes.
