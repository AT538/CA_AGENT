# PYQ Exam Analysis

An on-demand subsystem, separate from the daily current-affairs pipeline
(`../main.py`). It reads UPSC previous-year question papers
(`knowledge_base/pyqs.json`), uses an LLM to explain *why* each question was
asked — a syllabus-driven theme, a specific current event, or both — and
aggregates everything analyzed so far into a prediction of likely topics
and questions for a future exam year (2027 by default).

You run it whenever you want, against one paper, several, or everything —
it never runs automatically.

**Three docs, three purposes** (same convention as the main repo's own
`../README.md`):

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — how this subsystem works and
  why, including what it reuses from the main pipeline (`filter/retrieve.py`,
  `filter/llm_client.py`) versus what's new here.
- **[USER_GUIDE.md](./USER_GUIDE.md)** — step-by-step: prerequisites,
  configure, run locally, run on GitHub Actions on-demand, read the output.
- **[SKILL.md](./SKILL.md)** — not read by the pipeline itself; a reference
  for an AI assistant helping extend or debug this specific subfolder.
