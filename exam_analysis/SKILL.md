---
name: exam-analysis-maintenance
description: Reference for an AI assistant (Claude Code, or Claude in chat) helping maintain, extend, or debug the exam_analysis subsystem specifically. Load this whenever asked to change the analysis/prediction schema, add a provider, adjust caching, or explain a design decision in this subfolder.
---

# PYQ Exam Analysis — Maintenance Skill

## What this file is (and isn't)

Same convention as the main repo's `../SKILL.md` — this is **not** read by
any pipeline at runtime; `exam_analysis/run.py` is plain Python triggered
manually (CLI or `workflow_dispatch`), with no LLM agent loop deciding what
to do. The LLM's only role is the two structured calls in `analyzer.py`
and `predictor.py`.

This file exists for the *next* conversation about this subfolder — read
it first so you don't re-derive the design from scratch or accidentally
contradict an existing convention. For the main pipeline's own conventions
(sources, two-tier judging, PYQ filenames, etc.), see `../SKILL.md` — this
file only covers what's specific to `exam_analysis/`.

---

## Core design intent

Same owner/context as `../SKILL.md` describes. This subsystem's specific
job: given 20 years of actual UPSC PYQs, explain why each was asked
(syllabus vs. current-event driven) and predict likely future topics —
**on-demand**, not part of the daily automated pipeline.

Non-negotiables specific to this subsystem:

1. **Reuse, don't duplicate, the main pipeline's infrastructure.**
   `filter/retrieve.py` (embedding index) and `filter/llm_client.py`
   (provider registry/fallback) are shared, not forked. If a change here
   needs different retrieval or provider behavior, either the shared module
   grows a parameter, or the divergence is a strong signal the module
   shouldn't be shared for that case — don't just copy-paste and diverge.
2. **`knowledge_base/pyqs.json` is read-only input here.** This subsystem
   never fetches or parses PYQ PDFs itself — that's `knowledge_base/
   fetch_pyqs.py`/`parse_pyqs.py`'s job. If PYQ parsing needs to improve,
   fix it there, not in `exam_analysis/`.
3. **The cache (`analyzed_questions.json`) is the source of truth for
   prediction, always the FULL cache, never just the current run's
   selection.** Don't add a code path that predicts from a subset — the
   entire value of caching is that predictions get better as coverage grows.
4. **On-demand only — no cron.** Don't add a scheduled trigger to
   `exam_analysis.yml`; this is deliberately different from `daily.yml`.
5. **Analysis and prediction are separate LLM tiers with separate configs**
   (`exam_analysis.analysis_llm` / `exam_analysis.prediction_llm`),
   mirroring the daily pipeline's Tier 1/Tier 2 split — not because volume
   differs as dramatically here, but so provider/model choice for each can
   be tuned independently without code changes.

---

## The two LLM calls (what each answers)

`analyzer.py`'s `analyze_question()` — one call per question:
- `syllabus_topics` — grounded via `filter/retrieve.py`'s embedding index
  (same index the daily pipeline uses)
- `trigger` / `trigger_note` — **not** grounded; the LLM's own knowledge,
  since there's no local database of *past* years' news (the daily
  pipeline only accumulates going forward). Don't present `trigger_note`'s
  current-event claims as verified fact in any UI/output copy — the
  existing prompt already asks the model to flag low confidence, but
  nothing checks it.
- `why_asked` — free-text exam-setting rationale, not grounded, lower
  stakes than the above two fields.

`predictor.py`'s `build_prediction()` — one call per invocation, fed a
**computed frequency summary** (topic counts, all-time and recent-years-
weighted) plus example current-event-triggered questions, never the raw
question corpus. If asked to make predictions "smarter," the first lever is
improving what gets computed and handed to the model here (e.g. a better
recency weighting, per-paper breakdowns) — not switching to a bigger model.

---

## Conventions to follow when extending

- **Cache key scheme**: `"<year>_<paper>_<index>"`, where `index` is the
  question's position within that year+paper in `pyqs.json`'s file order
  (assigned by `run.py`'s `load_questions()`). This means **reordering
  `pyqs.json` entries for an already-analyzed year/paper invalidates that
  paper's cache keys** (they'll silently point at different questions).
  If `parse_pyqs.py`'s extraction order ever changes, treat every existing
  cache entry for affected papers as stale and re-run with `--force`.
- **New LLM provider**: add it to `filter/llm_client.py` (not here) — both
  `judge.py` and this subsystem pick it up automatically via
  `call_with_fallback()`.
- **Schema changes to `analyze_question()`'s output**: keep
  `ANALYSIS_PROMPT_TEMPLATE` (analyzer.py), the cache entries it produces,
  and `notion_writer.py`'s `build_analysis_blocks()` in sync — same
  lockstep-update requirement `../SKILL.md` describes for the daily
  pipeline's judgment schema.
- **Schema changes to `build_prediction()`'s output**: keep
  `PREDICTION_PROMPT_TEMPLATE` (predictor.py) and
  `notion_writer.py`'s `build_prediction_blocks()` in sync.
- **Adding a new CLI flag**: `run.py`'s `argparse` setup, `main()`'s
  validation logic, and `USER_GUIDE.md`'s usage examples should all be
  updated together — the flags are the only interface most users will
  ever see, and the `--year`/`--paper`/`--all`/`--predict-only` combination
  logic in `main()` is easy to make inconsistent if extended carelessly.

---

## What NOT to do

- Don't fork `filter/retrieve.py` or `filter/llm_client.py` into a
  subsystem-local copy — extend the shared module instead (see Core design
  intent #1).
- Don't add a scheduled trigger to `exam_analysis.yml` — this subsystem is
  on-demand by design (see main repo's `../SKILL.md` for the general "don't
  add cost without flagging the tradeoff" principle; an unnecessary
  schedule is the same category of mistake even at zero marginal $ cost,
  since it burns free-tier quota for no benefit).
- Don't predict from anything less than the full cache — see Core design
  intent #3.
- Don't present `trigger`/`trigger_note` current-event claims as verified —
  they're ungrounded LLM knowledge, unlike `syllabus_topics`.
- Don't switch the cache from JSON to something else without re-reading
  `ARCHITECTURE.md` §7's reasoning first — the tradeoff was deliberate at
  this data scale, not an oversight.
