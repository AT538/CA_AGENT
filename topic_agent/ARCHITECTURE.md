# Topic Agent — Architecture

This document explains *how this subsystem works and why* — for "how do I
actually run this," see **USER_GUIDE.md**. It assumes you've read the main
repo's **../ARCHITECTURE.md** first (and ideally `../exam_analysis/
ARCHITECTURE.md`, which this doc's structure mirrors) — vocabulary like
retrieval, tiers, and the fallback chain isn't re-explained here.

---

## Goal

You have your own study material for each UPSC subject — books, coaching
notes, articles — sitting on your machine. This subsystem lets you drop
that material in, organized by subject, and then ask for any topic by
name: it retrieves the most relevant pieces of *your own* material, cross-
references it against the UPSC syllabus and 20 years of PYQs, and writes
you a Mains-ready study summary plus a ready-to-use model answer — then
publishes it to Notion.

Like `exam_analysis`, this is **on-demand, not scheduled** — you ask for a
topic when you're studying it, not on a fixed cadence.

---

## 1. High-level flow

```
 topic_agent/sources/<Subject>/*.{pdf,txt,md}   (files YOU drop in - your
                                                  own books/notes/articles,
                                                  organized by subject)
   --> build_index.py   (LOCAL ONLY - extract text, chunk, embed, index)
   --> topic_agent/index/   (committed to git - a Chroma collection,
                              "topic_sources", separate from the main
                              repo's syllabus+PYQ index)

 --topic "<name>"  (CLI, run whenever you want)
   --> RETRIEVE (your sources)     topic_agent/retrieve.py, top-k from
                                    topic_agent/index/
   --> RETRIEVE (syllabus + PYQ)   filter/retrieve.py, top-k from
                                    knowledge_base/index/ (reused as-is)
   --> GENERATE                    one LLM call combining both retrieved
                                    contexts -> {topic_summary, mains_answer,
                                    syllabus_linkage, relevant_pyqs, sources_used}
   --> CACHE                       topic_agent/generated_topics.json,
                                    committed - re-asking the same topic is free
   --> PUBLISH                     one new Notion page per topic request
```

Orchestrated by `topic_agent/run.py`, triggered manually — locally, or via
a `workflow_dispatch` GitHub Actions workflow.

---

## 2. Two indexes, two purposes — don't conflate them

This subsystem introduces a **second** embedding index, entirely separate
from the main repo's `knowledge_base/index/`:

| | `knowledge_base/index/` (main repo) | `topic_agent/index/` (this subsystem) |
|---|---|---|
| Collection name | `upsc_knowledge` | `topic_sources` |
| Contents | `syllabus.json` + `pyqs.json` — fixed, curated by the repo | Whatever *you* drop into `topic_agent/sources/<Subject>/` |
| Built by | `knowledge_base/build_syllabus_index.py` | `topic_agent/build_index.py` |
| Rebuild cadence | Rarely — only when syllabus/PYQs change | Whenever you add/change your own material |
| Read by | daily pipeline, `exam_analysis`, **and** this subsystem | only this subsystem |

**Why two indexes instead of dumping everything into one?** They're
fundamentally different corpora with different lifecycles — the syllabus/
PYQ set is a fixed, shared, repo-curated reference; your own uploaded
sources are personal, growing, and specific to whatever you're currently
studying. Keeping them separate means rebuilding one never touches the
other, and a query can ask "what does *my* material say" and "what does
UPSC's own syllabus/PYQ pattern say" as two distinct, clearly-labeled
signals fed into the same generation prompt — rather than one blended,
unlabeled retrieval that the LLM can't tell apart.

Both indexes use the same local embedding model
(`sentence-transformers`, `bge-small-en-v1.5`) — no reason to diverge there,
it's free and consistent.

---

## 3. Ingesting your own sources

`topic_agent/build_index.py` (mirrors `knowledge_base/build_syllabus_index.py`'s
"full rebuild each time" pattern — see that file's own docstring for the
reasoning): scans `topic_agent/sources/<Subject>/`, extracts text from
`.pdf` (via the shared `ingest/pdf_utils.py`, also used by the main
pipeline's `monthly_pdfs.py` and `parse_pyqs.py`) or reads `.txt`/`.md`
directly, chunks into ~500-word pieces (same chunk size as the main
pipeline's monthly PDFs, for consistency), and embeds every chunk tagged
with `{subject, source_file, chunk_index}`.

**This step must run locally, never in CI.** Your uploaded source files
are gitignored (see §6) — a GitHub Actions runner's checkout never has
them, so `--rebuild-index` there would only ever see an empty `sources/`
directory. `build_index.py` guards against this explicitly: **if scanning
turns up zero chunks, it leaves any existing index untouched rather than
deleting it** — this was a real footgun caught during design (a naive
"delete then rebuild" would silently wipe out your real, already-committed
index the moment it ran anywhere `sources/` is empty).

---

## 4. Generation (per topic request)

`topic_agent/generator.py`'s `generate_topic_answer()` does two retrievals,
then one LLM call:

1. `topic_agent/retrieve.py` → top-k chunks from **your own** uploaded
   sources for this topic (optionally filtered to one `--subject`, via a
   Chroma metadata `where` filter).
2. `filter/retrieve.py`'s `retrieve_context()` (reused, unmodified) → top-k
   chunks from the syllabus/PYQ index — same function the daily pipeline
   and `exam_analysis` call.
3. Both contexts, clearly labeled and kept separate in the prompt, go to
   one LLM call:

```json
{
  "topic_summary": "revision-note-style summary, drawing on your sources",
  "mains_answer": "~200-250 word model answer, intro-body-conclusion",
  "syllabus_linkage": ["which syllabus topic(s) this maps to"],
  "relevant_pyqs": ["actual past questions on/near this topic, quoted"],
  "sources_used": ["which of your uploaded files were actually drawn on"]
}
```

**If you haven't uploaded anything yet (or nothing matches), generation
still works** — `retrieve_topic_sources()` raises a clear error when the
index doesn't exist, which `generator.py` catches and degrades gracefully:
it proceeds with syllabus/PYQ grounding alone and prints a one-line
warning, rather than crashing the whole request over a missing personal
index.

**Why one LLM call, not two tiers like the daily pipeline / `exam_analysis`?**
Those subsystems tier because volume differs sharply between stages
(everything vs. only-the-relevant-subset). Here, every `--topic` request
is already a single, deliberate, user-triggered ask — there's no
high-volume stage to keep cheap by deferring the expensive one. One call
is the right shape for this access pattern.

---

## 5. Caching

`topic_agent/cache.py` — flat JSON keyed by `"<subject|_>::<normalized topic>"`.
Re-requesting an already-generated topic **republishes the cached result
to Notion** rather than doing nothing — useful if a previous Notion publish
failed, or you just want another copy. `--force` regenerates from scratch.

Same reasoning as `exam_analysis/cache.py` for choosing flat JSON over
SQLite: topic-request volume here is small and manually-driven, not a
growing daily stream.

---

## 6. Output

`topic_agent/notion_writer.py` — one new Notion page per `--topic` request,
titled `<topic> (<subject if given>) — YYYY-MM-DD`, to its own page
(`config.yaml` → `notion.topic_agent_page_id`) — **separate from both** the
daily digest's page and `exam_analysis`'s page. Three independent output
streams, three independent Notion pages, so none of them mix.

---

## 7. Model choice & provider fallback

Reuses `filter/llm_client.py` verbatim (the same registry/rotation/fallback
chain as the daily pipeline and `exam_analysis`), configured via
`config.yaml` → `topic_agent.generation_llm`. Defaults to the same
free-tier chain as the rest of the repo.

---

## 8. Persistence

| What | Where | Why |
|---|---|---|
| Your uploaded source files | `topic_agent/sources/<Subject>/`, **gitignored** | Personal study material - potentially copyrighted books/notes; only the extracted/embedded chunks matter downstream, same reasoning as `knowledge_base/monthly_pdfs/*/`'s gitignored PDFs |
| Your sources' embedding index | `topic_agent/index/`, **committed** | What generation actually reads, locally and in CI - must survive a CI runner never seeing `sources/` |
| Generated-topic cache | `topic_agent/generated_topics.json`, **committed** | Same reasoning as `exam_analysis`'s cache and `data/articles.db` - CI runners are ephemeral |
| Syllabus/PYQ index | `knowledge_base/index/` (main repo, reused) | Not duplicated - same index the daily pipeline and `exam_analysis` already read |
| Generated summaries/answers | Notion | Permanent, readable archive |

---

## 9. Repo structure

```
topic_agent/
  README.md              (index - links to the 3 docs below)
  ARCHITECTURE.md          (this file)
  USER_GUIDE.md             how to run it
  SKILL.md                    maintenance/extension reference for an AI assistant
  __init__.py
  sources/                      <- you drop files here, one folder per subject (gitignored)
    <Subject>/*.pdf|*.txt|*.md
  build_index.py                 scans sources/, embeds into topic_agent/index/ (LOCAL ONLY)
  retrieve.py                     queries topic_agent/index/ for a topic string
  generator.py                     combines both retrievals -> one LLM call -> structured answer
  cache.py                          local JSON cache, keyed by subject::topic
  notion_writer.py                   publishes one page per topic request
  run.py                               CLI entrypoint (--topic/--subject/--rebuild-index/--list-subjects/--force)
  index/                                 committed Chroma index ("topic_sources" collection)
  generated_topics.json                   the cache itself (committed, grows over time)

ingest/
  pdf_utils.py            shared PDF-extraction/chunking (also used by monthly_pdfs.py, parse_pyqs.py)

filter/
  llm_client.py           shared provider registry + fallback chain (also used by judge.py, exam_analysis)
  retrieve.py                embedding search over the syllabus/PYQ index (also used by the daily pipeline, exam_analysis)

.github/workflows/
  topic_agent.yml         workflow_dispatch - generation only, no index-rebuild input (see §3)
```

---

## 10. Design decisions & tradeoffs worth understanding

- **A second, separate index rather than merging into `knowledge_base/index/`**:
  discussed in §2 — different corpus, different owner, different lifecycle.
  The tradeoff is one more moving piece (two indexes to keep straight), but
  conflating a fixed shared reference with your own growing personal
  material would make both harder to reason about.
- **Index-rebuild is explicitly local-only, with a hard safety guard**: the
  alternative (letting CI attempt a rebuild) risks silently destroying your
  real index the moment `sources/` is empty in that environment - which it
  always is in CI, given the gitignore. Making this impossible by design
  (no `rebuild_index` input in the workflow, plus the empty-scan guard in
  code) is safer than documentation alone.
- **One LLM call per topic, not tiered**: see §4 - tiering exists to control
  cost across *volume*, and there's no volume differential here worth
  optimizing for.
- **Source files gitignored, index committed**: mirrors the main repo's own
  `monthly_pdfs/`/`pyqs/raw/` convention exactly (raw downloads gitignored,
  derived index/JSON committed) - not a new pattern, just applied to a new
  kind of source.

---

## 11. Possible areas of improvement

1. **Incremental indexing.** `build_index.py` re-embeds everything on every
   rebuild, same as `build_syllabus_index.py`. Fine at personal-study-
   material scale (dozens to low hundreds of files), but a
   processed-marker scheme (like `ingest/monthly_pdfs.py`'s `.processed/`
   dir) would let you add one new file without re-embedding everything
   else, once your source library grows large enough for full rebuilds to
   feel slow.
2. **Source-file de-duplication across subjects.** If the same book chapter
   gets dropped into two subject folders by mistake, nothing currently
   catches that - both copies get embedded and could both surface in
   retrieval.
3. **Answer length/format control.** `mains_answer` is currently a fixed
   ~200-250 word target regardless of question type - a `--marks 10|15`
   flag mirroring UPSC's actual mark-based word limits would make the
   output map more precisely to a specific exam question format.
4. **Feeding `exam_analysis`'s per-topic PYQ frequency data into
   generation** - right now this subsystem does its own independent PYQ
   retrieval; cross-referencing `exam_analysis/analyzed_questions.json`
   (if it's been populated) could let the model note "this topic has come
   up 4 times in the last 8 years" directly in the summary.
