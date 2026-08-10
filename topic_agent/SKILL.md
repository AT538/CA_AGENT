---
name: topic-agent-maintenance
description: Reference for an AI assistant (Claude Code, or Claude in chat) helping maintain, extend, or debug the topic_agent subsystem specifically. Load this whenever asked to change the generation schema, touch the index-rebuild logic, add a provider, or explain a design decision in this subfolder.
---

# Topic Agent — Maintenance Skill

## What this file is (and isn't)

Same convention as `../SKILL.md` and `../exam_analysis/SKILL.md` — not
read by any pipeline at runtime. `topic_agent/run.py` is plain Python
triggered manually (CLI or `workflow_dispatch`); the LLM's only role is the
single structured call in `generator.py`.

Read this before touching this subfolder, so you don't re-derive the
design or contradict an existing convention. For the main pipeline's
conventions, see `../SKILL.md`; for `exam_analysis`'s, see
`../exam_analysis/SKILL.md` — this file only covers what's specific to
`topic_agent/`.

---

## Core design intent

Same owner/context as `../SKILL.md` describes. This subsystem's specific
job: let the owner drop in their *own* study material per subject, and on
request for any topic, produce a Mains-ready summary + model answer
grounded in that material plus the syllabus/PYQ set — **on-demand**, never
part of the daily automated pipeline.

Non-negotiables specific to this subsystem:

1. **Two indexes, never merged.** `topic_agent/index/` (collection
   `topic_sources`, this subsystem's uploaded material) and
   `knowledge_base/index/` (collection `upsc_knowledge`, the main repo's
   fixed syllabus+PYQ set) are retrieved separately and kept labeled
   separately in the generation prompt. Don't add code that writes into
   `knowledge_base/index/` from here, or that merges the two collections —
   see `ARCHITECTURE.md` §2 for why.
2. **Index-rebuild is LOCAL ONLY — this is a hard safety requirement, not
   a suggestion.** `topic_agent/sources/` is gitignored (see §"What NOT to
   do" below for why this matters). `build_index.py` MUST keep its
   guard that refuses to touch an existing index when a scan finds zero
   chunks — this is what prevents a CI run (which never has the raw
   source files) from silently wiping a real, committed index. Never
   remove or weaken this guard, and never add a `rebuild_index` input to
   `.github/workflows/topic_agent.yml`.
3. **`generate_topic_answer()` must degrade gracefully if the
   topic_sources index doesn't exist.** `retrieve_topic_sources()` raising
   is expected (e.g. before the owner's first `--rebuild-index`) — the
   caller catches it and proceeds with syllabus/PYQ grounding alone. Don't
   turn this into a hard failure.
4. **One LLM call per topic request, not tiered.** Unlike the daily
   pipeline and `exam_analysis`, there's no high-volume stage to protect
   here — every request is already a deliberate, single, user-triggered
   ask. Don't add tiering without a genuine volume-differential reason.
5. **Reuse `filter/llm_client.py` and `filter/retrieve.py` as-is.** Don't
   fork either into a subsystem-local copy.

---

## The one LLM call (what it answers)

`generator.py`'s `generate_topic_answer()` — one call per `--topic`
request, fed two separately-labeled retrieved contexts (your sources +
syllabus/PYQ), producing:

- `topic_summary` — grounded in your uploaded sources where relevant
  (via `topic_agent/retrieve.py`, embedding-based, traceable)
- `mains_answer` — same grounding, formatted as an exam-ready answer
- `syllabus_linkage` — grounded via `filter/retrieve.py` (same index the
  daily pipeline uses)
- `relevant_pyqs` — grounded the same way, expected to be *quoted*, not
  paraphrased, from the matched PYQ context
- `sources_used` — the model's own accounting of which uploaded files it
  actually drew on; not independently verified

If asked to improve output quality, the first lever is retrieval quality
(better chunking of uploaded sources, more relevant `top_k`, correct
`--subject` filtering) before reaching for a bigger model — same general
principle `../SKILL.md` states for the main pipeline.

---

## Conventions to follow when extending

- **Chunk metadata scheme**: `{subject, source_file, chunk_index}` on
  every `topic_sources` chunk, set in `build_index.py`'s `collect_chunks()`.
  `topic_agent/retrieve.py`'s `--subject` filter depends on the `subject`
  key exactly matching a folder name under `topic_agent/sources/` — don't
  rename this key without updating both sides.
- **New LLM provider**: add it to `filter/llm_client.py` (not here) —
  picked up automatically by `call_with_fallback()`.
- **Schema changes to `generate_topic_answer()`'s output**: keep
  `GENERATION_PROMPT_TEMPLATE` (generator.py) and `notion_writer.py`'s
  `build_blocks()` in sync — same lockstep-update requirement the other
  two subsystems' SKILL.md files describe for their own schemas.
- **Supporting a new source file format**: add the extension to
  `build_index.py`'s `SUPPORTED_SUFFIXES` and `run.py`'s
  `SUPPORTED_SUFFIXES` (kept in both places deliberately - `run.py`'s
  copy is only used for `--list-subjects` display, not indexing, so a
  mismatch between the two just means `--list-subjects` under/over-counts
  files, not a functional bug - but keep them in sync anyway), and add
  extraction logic to `build_index.py`'s `_extract_text()`.
- **Cache key scheme**: `"<subject|_>::<normalized topic>"` via
  `cache.normalize_key()`. Changing the normalization (e.g. adding stemming)
  invalidates every existing cache entry's key silently — old entries
  become permanently unreachable, not erroring, so this kind of change is
  easy to miss the impact of. Flag it explicitly if you make one.

---

## What NOT to do

- **Don't remove `topic_agent/sources/*/*.{pdf,txt,md}` from `.gitignore`.**
  These are the owner's personal study material - potentially copyrighted
  book PDFs. Committing them isn't just a repo-hygiene issue, it's a
  content-distribution one. Only the derived, embedded chunks
  (`topic_agent/index/`) are meant to leave the local machine into git.
- **Don't add a `rebuild_index` input to the GitHub workflow** — see Core
  design intent #2. If asked for this, explain the underlying reason
  (gitignored sources, safety guard) rather than just doing it.
- **Don't merge `topic_agent/index/` and `knowledge_base/index/` into one
  collection** — see Core design intent #1.
- **Don't present `sources_used` as verified** - it's the model's own
  self-report of what it drew on, not independently checked against the
  retrieved chunks.
- **Don't add a paid API dependency without flagging the cost tradeoff** -
  same principle as `../SKILL.md` states for the main repo.
