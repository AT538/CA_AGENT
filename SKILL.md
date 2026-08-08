---
name: upsc-current-affairs-agent-maintenance
description: Reference for an AI assistant (Claude Code, or Claude in chat) helping maintain, extend, or debug this specific repo. Load this whenever asked to add a source, change the relevance criteria, modify the output format, or explain a design decision in this codebase.
---

# UPSC Current Affairs Agent — Maintenance Skill

## What this file is (and isn't)

This is **not** read by the daily pipeline itself — `main.py` runs as plain
scheduled Python via GitHub Actions, with no LLM agent loop deciding what to
do at runtime. The LLM's only role in the running system is the single
structured judgment call in `filter/judge.py` (see `PROMPT_TEMPLATE` there),
which is a separate, already-tuned prompt — don't confuse the two.

This file exists for the *next* conversation about this repo: when you (an
AI assistant) are asked to add a source, tweak relevance criteria, change
the output schema, or explain why something is built a certain way, read
this first so you don't have to re-derive the design from scratch or
accidentally contradict an existing convention.

---

## Core design intent

The owner is a UPSC Civil Services aspirant with a technical background
(software developer), building this as a personal side project. The
system's job: read a fixed set of sources daily/periodically, decide what's
genuinely relevant to the **full UPSC syllabus (Prelims + Mains GS1-4 +
Ethics + Essay)** using **20 years of Prelims + Mains previous question
papers** as grounding evidence, and produce output that's directly usable
for exam prep — not just "here are some news links."

Non-negotiables established across the build:

1. **Free-tier LLM only** for the judging step — this must keep working on
   Groq/Gemini/OpenRouter free tiers, not assume access to a paid frontier
   model. Any prompt or schema change should be tested against this
   constraint.
2. **Zero ongoing infra cost** — GitHub Actions + committed SQLite/Chroma,
   no paid server, no paid database (unless the owner explicitly decides to
   upgrade — see ARCHITECTURE.md's improvements section for that discussion).
3. **Config over code** — sources, LLM provider, and retrieval parameters
   live in `config.yaml`. Adding a source should not require touching
   Python unless it's a genuinely novel ingestion mechanism.
4. **Output must be exam-actionable**, not just informational. Every
   relevant item carries: a factual summary (replaces reading the source),
   a syllabus linkage, probable exam questions, where it's applicable
   (which GS paper/Essay/Ethics case study), and a ready-to-cite example
   for Mains/Essay answers. If asked to change the output schema, preserve
   this "actually usable in an answer" property — don't regress to a plain
   link list.
5. **Two-tier LLM calls, not one call per item.** The harder/generative
   fields only run on items already confirmed relevant, specifically so
   Tier 2 can use a stronger model without inflating the cost of Tier 1's
   high-volume relevance pass. See the dedicated convention below.

---

## Sources (current set — check config.yaml for the live list)

**Daily**: PIB, The Hindu (Editorial + National), Indian Express
(Explained), Down To Earth, PRS Bill Track.

**Monthly PDF**: Yojana, Kurukshetra, PRS Monthly Policy Review (all
auto-fetch attempted), Vision IAS Monthly Magazine (manual-only — behind a
paywall/login, do not attempt to build a scraper that bypasses this).

**Annual PDF**: Union Budget, Economic Survey (auto-fetch attempted, once/year).

When asked to add a source, first determine which of these three categories
it fits and follow the existing pattern for that category (see
USER_GUIDE.md, "Adding a new item" section) rather than inventing a new
ingestion path.

---

## The judgment approach (what "relevant" means here)

The retrieval step (`filter/retrieve.py`) surfaces the top-k syllabus/PYQ
chunks most semantically similar to an incoming item. The LLM judge
(`filter/judge.py`) then decides relevance **using that retrieved context**,
not from general knowledge — this is deliberate: relevance should be
traceable to an actual syllabus line or PYQ pattern, not the model's vague
sense of "this seems UPSC-ish."

If asked to improve judgment quality, prefer improving retrieval (better
chunking, more PYQ coverage, auto-tagging PYQ topics) over just swapping in
a bigger LLM — see ARCHITECTURE.md for why this pipeline is designed to
make a free-tier model sufficient.

The five output fields (`summary`, `relevance_note`, `probable_questions`,
`applicability`, `answer_example`) each answer a different question:

- `summary` — what happened (the facts)
- `relevance_note` — why it's on this list (syllabus/PYQ tie-in)
- `probable_questions` — what UPSC might ask about it
- `applicability` — where to use it (which paper/Essay/Ethics case study)
- `answer_example` — the actual line to drop into an answer

Keep these separated if extending the schema — don't collapse them back
into one blended field; that was an explicit fix requested during the
build (an earlier version blended fact + relevance into one muddy "note"
field, which made the digest read like an index rather than something the
owner could revise from directly).

---

## Conventions to follow when extending

- **Two-tier LLM design is deliberate — preserve it.** Tier 1
  (`judge_relevance`) runs on every incoming item and must stay cheap/free.
  Tier 2 (`generate_exam_angle`) runs only on the relevant subset and is
  configured separately (`config.yaml` → `llm.exam_angle`) specifically so
  it can point at a stronger model without inflating Tier 1's cost. If
  asked to improve exam-angle quality, the first lever is bumping
  `llm.exam_angle`'s model/provider — not touching Tier 1.
- **PYQ filenames**: `<year>_<paper>.pdf` where paper is one of
  `prelims_gs1`, `mains_gs1`, `mains_gs2`, `mains_gs3`, `mains_gs4`. Both
  `fetch_pyqs.py` and `parse_pyqs.py` rely on this exact pattern.
- **Syllabus entries**: one sub-topic per JSON object
  (`id`/`paper`/`topic`/`description`) — never merge multiple sub-topics
  into one entry, it degrades retrieval precision.
- **New LLM provider**: add one function in `filter/judge.py` following the
  existing `_call_groq`/`_call_gemini` signature `(prompt, model) -> str`,
  register it in `_PROVIDERS`, done — usable by either tier immediately
  since both route through the same `_call_with_fallback`.
- **Schema changes to judgment output**: Tier 1 fields
  (`relevant`/`gs_paper`/`topics`/`summary`/`relevance_note`) live in
  `RELEVANCE_PROMPT_TEMPLATE`; Tier 2 fields
  (`probable_questions`/`applicability`/`answer_example`) live in
  `EXAM_ANGLE_PROMPT_TEMPLATE`. If you add/rename a field, update in
  lockstep: the relevant prompt template, the matching fallback dict
  (`judge_relevance()`'s or `generate_exam_angle()`'s), and the rendering
  logic in `output/notion_writer.py` — these must stay in sync or the
  pipeline will crash or silently drop the new field.
- **New monthly/annual PDF source**: add to `config.yaml` under
  `monthly_pdf_sources` or `annual_pdf_sources`; only write new scraping
  logic in `ingest/monthly_pdfs.py` if the generic "first `.pdf` link on the
  listing page" heuristic genuinely fails for that site.

---

## What NOT to do

- Don't add a paid API dependency (embeddings, vector DB, LLM) without
  flagging the cost tradeoff explicitly — the whole system is designed
  around zero ongoing cost.
- Don't attempt to bypass Vision IAS's login/paywall — it's intentionally
  manual-only.
- Don't collapse the five-field judgment schema back into a single
  free-text note — this was a deliberate design correction, not an
  arbitrary choice.
- Don't assume a frontier/paid model is needed to fix a relevance-quality
  problem — check whether it's actually a retrieval problem first (weak
  syllabus chunking, missing PYQ coverage, low `top_k`).
