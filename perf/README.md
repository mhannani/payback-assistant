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
make perf BASE_URL=https://<cloud-run-url>  # or point it at a deployed instance
```

## What it measures

- **Latency** — every request is timed end to end → **p50 / p95 / p99** + throughput.
- **Cost** — each `/assist` response carries the turn's LLM cost in its `usage` block (token counts
  from LangChain, priced by LiteLLM — see [`app/llm/cost.py`](../apps/backend/app/llm/cost.py)). The
  client sums those real figures and scales to 1000.

The query mix is reused from [`demo/queries.json`](../demo/queries.json) so the load reflects real
intents (search, compare, route, vague→clarify, decline).

## Cost extrapolation

Cost per turn is ~constant (same prompt shape, similar token counts), so **cost-per-1000 scales
linearly** from the sample; the default run extrapolates and labels it as such, and `-n 1000` measures
it directly. Latency is bound by the single LLM call per turn (retrieval is sub-millisecond), so
model choice, prompt size, and caching drive performance more than application code.
