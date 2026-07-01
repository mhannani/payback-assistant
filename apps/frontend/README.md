# Frontend (additional, on a separate branch)

`main` scopes to the **backend core** — the microservice, recommendation engine, intent agent, and
deployment that make up the required deliverables — so it is evaluated on its own. The web UI is an
additional layer on the `feat/showcase-widget` branch, a thin client over the stable JSON API.

## What it provides

- A chat widget over the assistant API (`POST /assist` + `/assist/resume`).
- Rendering of the structured response: products as cards (name, partner, price, image), a
  price-per-unit comparison table, a partner hand-off, or a clarifying question.
- The multi-turn clarify flow, driven by the agent's pause/resume.
- Voice dictation (Deepgram) with German + English support.
