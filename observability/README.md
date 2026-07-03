# Observability — self-hosted Langfuse v3

Every agent LLM call is traced — model, tokens, latency, prompt and structured response — into a
self-hosted **Langfuse v3**, live at **https://langfuse.payback.mhannani.me**.

## How tracing is wired

One seam, no per-call-site instrumentation: every model call goes through the LiteLLM gateway
(`ChatLiteLLM`), and [`app/llm/tracing.py`](../apps/backend/app/llm/tracing.py) registers LiteLLM's
**`langfuse_otel`** callback once at startup. Langfuse v3 ingests OpenTelemetry spans (the
`success_callback=["langfuse"]` path is v2-only), so the backend ships the OTEL SDK + OTLP exporter
— not the `langfuse` package.

Off by default, and telemetry can never fail a turn: the wiring is gated on `LANGFUSE_ENABLED` and
try/except-wrapped — a Langfuse outage degrades to "no traces", never to a failed request.

## The stack ([docker-compose.langfuse.yml](docker-compose.langfuse.yml))

| Service | Role |
|---|---|
| `langfuse` (web) | Dashboard + ingest API — behind the shared Traefik at `langfuse.payback.mhannani.me` |
| `langfuse-worker` | Async ingestion: events → ClickHouse |
| `langfuse-postgres` | App DB (dedicated — Prisma migrations refuse a shared schema) |
| `langfuse-clickhouse` | OLAP store for traces / observations / scores |
| `langfuse-redis` | Queue + cache (`noeviction`, as Langfuse requires) |
| `langfuse-minio` | S3-compatible blob store for raw events (internal-only) |

Two deliberate isolation choices:

- **Own compose project** (`name: payback-langfuse`) — the app deploy runs
  `up -d --remove-orphans` on its own compose file; without a distinct project name that would
  treat these services as orphans and delete the tracing stack on every deploy.
- **Own internal network** — only the web service additionally joins the shared `traefik` network.
  The API posts traces in-network (`http://payback_langfuse:3000`), so they never leave the box.

The instance auto-provisions its org, project, API keys, and admin user from `LANGFUSE_INIT_*`
(no signup step). Those values come from the same env file the API reads, so the keys the instance
accepts and the keys the API sends can't drift.

## Run

```bash
# Server (secrets from .env.prod — see ../.env.prod.example for the block):
docker compose --env-file .env.prod -f observability/docker-compose.langfuse.yml up -d

# Local (dev defaults baked in; UI on http://localhost:3003):
docker network create traefik   # once, if absent
docker compose -f observability/docker-compose.langfuse.yml up -d
```

The app's deploy pipeline never touches this stack — bring it up/down independently.
