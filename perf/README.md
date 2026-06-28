# Performance

A small load-test client that drives `POST /assist` under concurrency and reports **latency
percentiles** and **cost per 1000 requests** — the brief's optional performance check.

## Run

With the stack up, the catalog embedded, and an LLM key set (`OPENAI_API_KEY` in `.env.dev`):

```bash
make perf                                   # 30 requests, 5 concurrent (a few cents)
```

Tune the load, or run the literal 1000:

```bash
python perf/run_perf.py -n 1000 -c 20       # the real 1000-request run
python perf/run_perf.py --base-url https://<your-url>
```

## What it measures

- **Latency** — every request is timed end to end → **p50 / p95 / p99** + throughput.
- **Cost** — each `/assist` response carries the turn's LLM cost in its `usage` block (token counts
  from LangChain, priced by LiteLLM — see [`app/llm/cost.py`](../apps/backend/app/llm/cost.py)). The
  client sums those real figures and scales to 1000.

The query mix is reused from [`demo/queries.json`](../demo/queries.json) so the load reflects real
intents (search, route, vague→clarify).

## Why extrapolate cost from a small N

Cost per turn is ~constant (same prompt shape, similar token counts), so **cost-per-1000 scales
linearly** from the sample — firing a literal 1000 calls costs ~30× more for the same number. The
default run extrapolates and labels it as such; `-n 1000` measures it directly when you want that.

Latency is bound by the single LLM call per turn (retrieval is sub-millisecond), so the levers for
faster/cheaper responses are model choice, prompt size, and caching — not the application code.
