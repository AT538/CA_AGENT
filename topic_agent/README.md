# Topic Agent

An on-demand subsystem, separate from both the daily current-affairs
pipeline (`../main.py`) and `../exam_analysis/`. You upload your own study
material per subject (books, notes, articles), and on request for any
topic, it retrieves the most relevant pieces of your material, cross-
references the UPSC syllabus and 20 years of PYQs, and writes a Mains-ready
study summary plus a model answer — published straight to Notion.

You run it whenever you're studying a topic — it never runs automatically.

**Three docs, three purposes** (same convention as `../README.md` and
`../exam_analysis/README.md`):

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — how this subsystem works and
  why, including the two-index design (your uploaded sources vs. the
  shared syllabus/PYQ index) and the safety guard around index rebuilding.
- **[USER_GUIDE.md](./USER_GUIDE.md)** — step-by-step: upload sources,
  build the index, run locally, run on GitHub Actions on-demand, read the output.
- **[SKILL.md](./SKILL.md)** — not read by the pipeline itself; a reference
  for an AI assistant helping extend or debug this specific subfolder.
