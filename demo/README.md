# Demo

A small client that drives the assistant with five queries — one per intent × language — and
prints the structured JSON it returns. It's a plain HTTP caller of `/assist` (and `/assist/resume`
for the clarifying-question turn), so it shows the agent exactly as a real client would use it.

## Run

With the stack up, the catalog embedded, and an LLM key set (`OPENAI_API_KEY` in `.env.dev`):

```bash
make up && make seed && make embed
make demo
```

`make demo` runs [`run_demo.py`](run_demo.py) inside the api container against the local service.
To demo a deployed instance instead:

```bash
python demo/run_demo.py --base-url https://<your-url>
```

## What it covers

The queries live in [`queries.json`](queries.json) (data, not code):

| Query | Shows |
|---|---|
| `günstige Windeln` | German, specific + price intent → ranked products |
| `pasta dinner` | English → German cross-lingual search across partners |
| `zeig mir Kaffee bei edeka` | navigational → hand-off (deep-link) to the partner's own search |
| `I want something to eat` | vague → clarifying question, then **resumed** with an answer |
| `vegane Schokolade` | German + dietary filter |
