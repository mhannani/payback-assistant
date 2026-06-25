# Frontend (additional, on a separate branch)

The `main` branch deliberately scopes to the **backend core** — the microservice,
recommendation engine, intent agent, and deployment that make up the required
deliverables. This keeps `main` focused and easy to evaluate on its own.

A web UI for the assistant is an **additional layer**, developed on a separate
branch rather than `main`, so the core scope stays clean and the UI can evolve
independently against the stable API.

## What it will provide

- A chat interface over the assistant API (`POST /assist` + `/assist/resume`).
- Rendering of the structured response: recommended products as cards
  (name, partner, price, and **product image**) or the clarifying question.
- The multi-turn clarify flow, driven by the agent's pause/resume.

## Why a separate branch

The backend returns a structured JSON contract, so the UI is a thin client on
top of it. Separating it means the backend can be evaluated and run on its own
(`make up`), while the UI is layered on top without expanding the core's scope.
