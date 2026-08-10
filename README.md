# UPSC Current Affairs Agent

Daily automated pipeline that reads UPSC sources — The Hindu, Indian
Express, PIB, PRS Monthly Policy Review, Vision IAS Monthly Magazine,
Union Budget & Economic Survey, Yojana, Kurukshetra, Down To Earth —
filters for relevance against the full UPSC syllabus (Prelims + Mains
GS1-4 + Ethics + Essay) and 20 years of previous question papers, and
publishes a new Notion page every day: plain-language summaries, a cue
back to the syllabus topic, probable exam questions, where each item is
applicable, and a ready-to-cite example for Mains/Essay answers.

**Three docs, three purposes:**

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — how the system works and why,
  written for someone new to agent-building. Includes a design-decisions
  section and a backlog of possible improvements.
- **[USER_GUIDE.md](./USER_GUIDE.md)** — step-by-step: install, configure,
  run locally, host on GitHub Actions, and the manual steps needed on an
  ongoing basis (Vision IAS drop-ins, PYQ downloads, etc).
- **[SKILL.md](./SKILL.md)** — not read by the pipeline itself; a reference
  for an AI assistant (Claude Code or a future chat) helping you extend or
  debug this repo, so the design intent doesn't have to be re-explained
  each time.

**Two related, on-demand subsystems** (separate from the daily pipeline
above — each has its own README/ARCHITECTURE/USER_GUIDE/SKILL docs):

- **[exam_analysis/](./exam_analysis/)** — analyzes 20 years of PYQs (why
  was each question asked) and predicts likely future-year topics/questions.
- **[topic_agent/](./topic_agent/)** — upload your own subject study
  material; ask for any topic and get a Mains-ready summary + model answer.
