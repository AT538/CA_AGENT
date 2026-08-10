# Topic Agent — User Guide

Step-by-step: upload your sources, build the index, run it locally, run it
on GitHub, and read the output. For *why* it's built this way, see
**ARCHITECTURE.md**.

---

## 1. Upload your sources

Create one folder per subject under `topic_agent/sources/`, and drop in
whatever study material you have — books, coaching notes, articles — as
`.pdf`, `.txt`, or `.md`:

```
topic_agent/sources/
  Polity/
    laxmikanth_ch5_federalism.pdf
    my_notes_centre_state.txt
  Economy/
    budget_2026_summary.pdf
  Environment/
    ...
```

Subject folder names are free-form — use whatever you'd naturally call
each subject (`Polity`, `Economy`, `Environment`, `Ethics`, `History`,
etc.). They show up later as the `--subject` filter and in the generated
output's "sources used" list.

**These files are gitignored** — they stay on your machine (or your CI
runner's local checkout, but see §4 for why rebuilding there doesn't
work). Only the *embedded index* built from them gets committed.

---

## 2. Build the index (after any upload, before your first `--topic` run)

```bash
python -m topic_agent.run --rebuild-index
```

This scans every subject folder, extracts text, chunks it, and embeds it
locally (no API cost — same embedding model the main pipeline uses). Full
rebuild each time, so re-run this whenever you add, remove, or change a
source file. You'll see a per-file chunk count:

```
  Polity/laxmikanth_ch5_federalism.pdf: 34 chunks
  Polity/my_notes_centre_state.txt: 2 chunks
  Economy/budget_2026_summary.pdf: 18 chunks
Index built: 54 chunks across 2 subject(s) -> topic_agent/index/
```

Check what's currently ingested at any time:

```bash
python -m topic_agent.run --list-subjects
```

**If you skip this step entirely**, `--topic` requests still work — they
just fall back to syllabus/PYQ grounding only, without your own material.
You'll see a one-line warning when that happens.

---

## 3. Generate material for a topic

```bash
# Basic
python -m topic_agent.run --topic "Federalism in India"

# Restrict retrieval to one subject's uploaded sources (useful if a topic
# name is ambiguous across subjects)
python -m topic_agent.run --topic "Green Hydrogen Mission" --subject Environment

# Regenerate even though it's already cached
python -m topic_agent.run --topic "Federalism in India" --force
```

Output: a new Notion page with a **Topic Summary** (revision-note style),
a **Mains Model Answer** (~200-250 words, ready to adapt), the **syllabus
linkage**, any **relevant PYQs** matched, and which of your uploaded
sources actually got used.

Asking for the same topic again without `--force` doesn't re-spend LLM
quota — it just republishes the cached result to a fresh Notion page.

---

## 4. Run it on GitHub (on-demand, not scheduled)

`.github/workflows/topic_agent.yml` is `workflow_dispatch`-only — no cron:

- **From the Actions tab**: repo → **Actions** → "Topic Agent - Mains
  Answer Generator (on-demand)" → **Run workflow** → fill in topic
  (required), subject (optional), force.
- **From the CLI**: `gh workflow run topic_agent.yml -f topic="Federalism in India"`

Uses the same repo secrets as the other workflows
(`GROQ_API_KEY`/`GEMINI_API_KEY`/`OPENROUTER_API_KEY`/`NOTION_TOKEN`, or
their `_KEYS` rotation variants).

**Important: there's no `--rebuild-index` option in this workflow, and
that's deliberate.** Your uploaded source files (§1) are gitignored, so a
GitHub Actions checkout never has them — CI can only ever *read* the
already-built, already-committed `topic_agent/index/`. Always build/update
the index locally (§2), then commit and push `topic_agent/index/` before
expecting CI runs to reflect your latest uploads.

---

## 5. Reading the output

Set `notion.topic_agent_page_id` in `config.yaml` to a page shared with
your Notion integration — **use a page different from** both the daily
digest's and `exam_analysis`'s page ids, so all three stay separate. Leave
it empty to skip Notion publishing (results still cache locally either way).

If nothing shows up in Notion, check:
- Is `notion.topic_agent_page_id` actually set?
- Did every configured LLM provider fail? Look for `[error]` in the console.
- Did generation produce empty fields? A `[warn]`-only run (all providers
  down) publishes nothing, by design (see `notion_writer.py`).

---

## 6. Ongoing usage patterns

- **New source material for a subject you're studying**: drop the file
  into its subject folder, `--rebuild-index`, commit `topic_agent/index/`.
- **A topic spans multiple subjects** (e.g. "Federalism" touches both
  Polity and Governance): omit `--subject` so retrieval searches across
  everything you've uploaded, not just one folder.
- **You want a second pass at a topic** after uploading more material:
  `--rebuild-index` first, then `--topic "..." --force`.
- **Cross-check with `exam_analysis`**: if you've been running
  `exam_analysis` on the same subject's PYQs, its trend analysis (which
  topics recur, which are current-event-driven) is a good companion input
  when deciding what to `--topic` next.
