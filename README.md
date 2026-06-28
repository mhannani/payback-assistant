# PAYBACK Assistant

Backend for a multilingual shopping assistant. One natural-language query (German or English) returns a
ranked list of products across three partner catalogs — dm, EDEKA, and Amazon — in one response.

## Motivation

PAYBACK connects shoppers to hundreds of partner businesses, each with its own catalog. A shopper
doesn't want to pick a partner first and search within it — they want to describe what they need and get
the best options, wherever they happen to be sold. That is awkward today: the catalogs differ in
structure and language, "best" mixes relevance with price and partner fairness, and a request can arrive
in German or English with no prior history to lean on.

This service is that single entry point. It accepts one free-text query and answers with products drawn
from every partner at once — bridging the catalogs at ingestion, matching meaning and exact terms across
languages, and ranking so no partner is unfairly buried or boosted.

Built so far: the recommendation engine — ingestion, indexing, and cross-catalog retrieval behind a
`/search` API. The intent agent and cloud deployment build on the interfaces it already exposes; see
[Status](#status).

## Example

Start the stack, load the catalogs, and ask for a pasta dinner — three commands, then one request:

```bash
make up && make seed && make embed
curl 'http://localhost:8000/search?q=pasta%20dinner&top_k=3'
```

The response is a ranked list of products — list order is the ranking. An English query returns German
products, drawn from two different partners:

```json
[
  { "partner": "edeka", "partner_name": "EDEKA", "name": "Panzani Spaghetti",
    "brand": "Ebro Foods", "price_cents": 1156, "currency": "EUR", "tags": ["vegetarian"] },
  { "partner": "edeka", "partner_name": "EDEKA", "name": "Spaghetti au Quinoa Persil Ail",
    "brand": "Jardin Bio", "price_cents": 861, "currency": "EUR", "tags": ["organic"] },
  { "partner": "amazon", "partner_name": "Amazon", "name": "Barilla Spaghetti N° 5 500g / dried pasta",
    "brand": "Barilla", "price_cents": 279, "currency": "EUR", "tags": [] }
]
```

(`id`, `description`, and `image_url` are also returned; trimmed here for readability.)

Everything runs offline on a local Docker stack — no API keys required.

---

## Contents

- [Status](#status)
- [Data model & ingestion](#data-model--ingestion)
- [Retrieval](#retrieval)
- [Intent agent](#intent-agent)
- [API](#api)
- [Running locally](#running-locally)
- [Evaluation & strategy configuration](#evaluation--strategy-configuration)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Testing](#testing)
- [Deployment](#deployment)
- [Limitations](#limitations)

---

## Status

| Task | Status |
|---|---|
| 1 — Recommendation engine | ✅ Done — ingestion adapters, embeddings, hybrid retrieval, fair cross-partner ranking, `/search`, eval harness |
| 2 — Intent agent | ✅ Done — LangGraph agent: intent + language classification → search / clarify / route, durable clarify/resume, `/assist` |
| 3 — Cloud deployment | ◻️ Not started — runs on Docker now; LLM, embedder, and vector store are config-switchable for GCP |

`/search` is a retrieval primitive: it does not parse intent from the query (it won't read "cheap" from
*günstige*). Intent classification and the clarifying-question branch live in the **intent agent** (Task 2,
`/assist`), which calls `/search`. Keeping that boundary explicit is what lets retrieval be tested on its own.

---

## Data model & ingestion

The three feeds share no schema — different field names, price formats, units, and metadata:

| | dm | EDEKA | Amazon |
|---|---|---|---|
| name | `title` | `name` | `product_name` |
| brand | `marke` | `hersteller` | `brand` |
| price | `4.26` (float €) | `"12,30"` (string) | `39.99` (float €) |
| size | free-text pack size | `"500 g"`, `"1,5 l"` | none |
| labels | Open Food Facts tags | Open Food Facts tags | none |
| id | `dm_gtin` | `ean` | `asin` |

A `PartnerAdapter` per partner (one implementation each, chosen by a registry) maps each feed into one
canonical `Product`. Normalization runs once, at load time — not per request:

- prices → integer cents, locale-aware via **Babel** (`"12,30"` → `1230`)
- sizes → grams / millilitres via **Pint** (`"1,5 l"` → `1500`)
- Open Food Facts labels → a curated dietary `tags` set (`organic`, `vegan`, …)
- partner-specific fields (asin, rating, gtin) → an opaque `attrs` JSONB column

Fields that can be compared (price, size) or filtered (tags, partner) become typed columns; everything
descriptive goes into a `description` that is embedded.

```text
 PARTNER FEEDS (disparate)                     INGESTION (offline · make seed + make embed)
 ┌─────────────────────────────────┐
 │ dm.json                         │           ┌───────────────────────────────────────────┐
 │   title · marke · price_eur     │──┐        │  Partner adapter  (ABC + 1 impl per partner)│
 │   pack_size · dm_gtin · labels  │  │        │   Babel  → price_cents   ("12,30" → 1230)   │
 ├─────────────────────────────────┤  │        │   Pint   → weight_g / volume_ml  ("1,5 l" → │
 │ edeka.json                      │  ├──────▶ │            1500 ml)                          │
 │   name · hersteller · "12,30"   │  │        │   labels → tags[]  (curated dietary set)    │
 │   weight "1,5 l" · ean · labels │  │        │   compose_description → embed text          │
 ├─────────────────────────────────┤  │        └───────────────────────┬─────────────────────┘
 │ amazon.json                     │  │                                 │ canonical Product
 │   product_name · brand · price  │──┘                                 ▼
 │   asin · rating · blurb (no size)│          ┌───────────────────────────────────────────────┐
 └─────────────────────────────────┘          │      PostgreSQL + pgvector  (products table)     │
                                               │  ┌────────────────────────────┬───────────────┐ │
   make embed ───────────────────────────────▶│  │ embedding VECTOR(384)       │ HNSW (cosine) │─┼─▶ semantic arm
   (Embedder → 384-d vector + provenance)      │  │ search_tsv (German tsvector)│ GIN           │─┼─▶ keyword arm
                                               │  │ tags TEXT[]                 │ GIN           │─┼─▶ require_tags filter
                                               │  │ weight_g · volume_ml · price│ (typed cols)  │─┼─▶ price-per-unit sort
                                               │  └────────────────────────────┴───────────────┘ │
                                               └───────────────────────────────────────────────────┘
```

One `products` table backs everything: an HNSW index for semantic search, a GIN index on a German
`tsvector` for keyword search, and GIN indexes on `tags` and `attrs`. Schema and embedding details are in
[docs/architecture.md](docs/architecture.md).

Embeddings are provider-agnostic (`Embedder` interface). The default is a local multilingual
sentence-transformer (`paraphrase-multilingual-MiniLM-L12-v2`, 384-d) baked into the image, so the
service runs without credentials; Vertex AI and OpenAI are config-swappable.

---

## Retrieval

A query runs two arms and fuses them. Each alone is insufficient: Postgres German full-text returns no
results for the English phrase `pasta dinner`, and vector search is weak on exact tokens like the brand
`Anker`.

- **Semantic arm** — pgvector cosine similarity (HNSW) over multilingual embeddings; handles meaning and
  cross-language matching.
- **Keyword arm** — Postgres German full-text (`websearch_to_tsquery` + `ts_rank`); handles exact terms,
  brands, and German stemming (`Windeln` → `Windel`).

The two ranked lists are merged with **Reciprocal Rank Fusion** (k=60; Cormack et al., 2009),
`score(d) = Σ 1/(k + rankᵢ(d))`. Fusing on rank rather than raw score avoids reconciling the arms'
incomparable scales and rewards products both arms return. With no user history, the query alone drives
the result.

```text
  GET /search?q=günstige Windeln & sort=price_low  (+ optional partner / require_tags)
                                 │
                       embed_query (sync, L2-normalized)
                                 │
            ┌────────────────────┴─────────────────────┐
            ▼                                            ▼
  ┌───────────────────────┐                  ┌───────────────────────────┐
  │  SEMANTIC ARM          │                  │  KEYWORD ARM               │
  │  cosine_distance       │                  │  websearch_to_tsquery(de)  │
  │  over HNSW → top k     │                  │  @@ search_tsv · ts_rank   │
  │         │              │                  │  (German stemming)         │
  │         ▼              │                  │         │                  │
  │  CandidateFilter       │                  │         ▼                  │
  │  absolute ceiling 0.50 │                  │  ts_rank ≥ min_rank floor  │
  │  (pre-fusion noise cut)│                  │                            │
  └───────────┬────────────┘                  └─────────────┬──────────────┘
              │  ranked id list                            │  ranked id list
              └──────────────────┬─────────────────────────┘
                                 ▼
              ┌──────────────────────────────────────────┐
              │  RECIPROCAL RANK FUSION                    │
              │  score(d) = Σ 1 / (k + rank),  k = 60      │
              └──────────────────┬───────────────────────┘
                                 ▼
                 load fused products (eager-load partner + brand)
                                 │
                                 ▼
              ┌──────────────────────────────────────────┐
              │  RANKER  (pluggable · owns final order)    │
              │  constrained → relevance, then per-partner │   ← RANKING_STRATEGY
              │   cap, then back-fill  (default)           │     also: mmr · zscore
              └──────────────────┬───────────────────────┘
                                 ▼
                        sort == price_low ?
                        │ yes               │ no
                        ▼                   │
       re-order relevant set by             │
       price-per-unit (g vs ml vs           │
       raw cents — never interleaved)       │
                        └─────────┬─────────┘
                                  ▼
              list[ProductOut]  ·  id · partner · name · brand
                                   price_cents · currency · tags · score
```

Two stages decide quality, both selectable by config:

- **Candidate filter** — ANN always returns the nearest N, including irrelevant ones. The default
  `absolute` filter drops candidates past a cosine-distance ceiling before fusion, so a query with no good
  match returns nothing rather than noise. Alternatives: `autocut`, `relative`, `none`.
- **Ranker** — the default `constrained` ranker sorts by relevance, caps each partner's share of the
  results, then back-fills. `sort=price_low` re-orders the selected set by price-per-unit (comparing only
  like units) without overriding relevance. Alternatives: `mmr`, `zscore`.

Each decision, with alternatives, is an ADR:

| ADR | Decision |
|---|---|
| [0001](docs/decisions/0001-hybrid-retrieval-with-rrf.md) | Hybrid retrieval fused with RRF |
| [0002](docs/decisions/0002-fair-cross-partner-ranking.md) | Constrained cross-partner ranking, not per-source normalization |
| [0003](docs/decisions/0003-pgvector-with-retriever-interface.md) | pgvector behind a `Retriever` interface; warehouse as the production path |
| [0004](docs/decisions/0004-provider-agnostic-embeddings.md) | Provider-agnostic embeddings |
| [0005](docs/decisions/0005-candidate-filtering.md) | Candidate filtering to cut the vector noise tail |
| [0006](docs/decisions/0006-intent-agent-langgraph.md) | Intent agent as a LangGraph state machine |

---

## Intent agent

The agent turns a raw query into an action. It is a **LangGraph** state machine: an LLM classifies
intent and language, a small policy picks the next action, and the agent returns a structured
response — products, a clarifying question, or a hand-off to a partner's own search.

<p align="center">
  <img src="docs/images/agent_graph.png" alt="Agent graph" width="360">
</p>

- **search** — a concrete request (e.g. `günstige Windeln`) → runs `/search` and returns products.
  If nothing matches, it asks the user to refine rather than returning an empty list.
- **clarify** — a vague request (e.g. `ich suche etwas`) → asks one question and **pauses**
  (`interrupt`); the client answers via `/assist/resume` and the agent continues the same thread.
- **route** — a navigational request (e.g. `Kaffee bei edeka`) → hands off a deep-link into that
  partner's own product search.

The LLM is reached through a LiteLLM gateway, so the provider is a config choice (`LLM_MODEL`,
default `openai/gpt-4o-mini`). Conversation state is persisted in Postgres (`AsyncPostgresSaver`), so
a paused clarify survives a restart and works across instances. See
[ADR 0006](docs/decisions/0006-intent-agent-langgraph.md).

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /assist` | Natural-language query → products, a clarifying question, or a partner hand-off |
| `POST /assist/resume` | Answer a clarifying question and continue the conversation |
| `GET /search` | Search across all partner catalogs (the mechanical primitive the agent drives) |
| `GET /health` | Liveness probe |
| `GET /ready` | Readiness probe (checks the database) |

`POST /assist` takes `{ "query": "..." }` and returns one of three shapes, tagged by `type`:
`products` (a ranked list), `clarify` (a `question` + a `thread_id` to resume with), or `route`
(a `deeplink` into a partner's search). `POST /assist/resume` takes `{ "thread_id", "answer" }`.

`GET /search` parameters:

| Param | Type | Default | Meaning |
|---|---|---|---|
| `q` | string (required) | — | Query, German or English |
| `top_k` | int 1–50 | 10 | Number of results |
| `partner` | `dm`\|`edeka`\|`amazon` | — | Restrict to one partner |
| `sort` | `relevance`\|`price_low` | `relevance` | Order within the relevant set |
| `require_tags` | list[string] | — | Keep only products with these dietary tags |

Response items (`ProductOut`): `id`, `partner`, `partner_name`, `name`, `brand`, `description`,
`price_cents`, `currency`, `image_url`, `tags`. Result order is the ranking.

---

## Running locally

Requires Docker. From the repository root:

```bash
make up      # start the API + Postgres/pgvector
make seed    # load the partner catalogs
make embed   # compute embeddings (required before search returns results)
make test    # run the test suite
```

See the whole assistant at once — five queries across languages and intents (incl. a
clarify→resume turn), printing the JSON (needs an LLM key in `.env.dev`):

```bash
make demo    # → demo/run_demo.py
```

Or hit `/search` directly, each query exercising a different path:

```bash
curl 'http://localhost:8000/search?q=Windeln'                        # German keyword
curl 'http://localhost:8000/search?q=pasta%20dinner'                # English → German
curl 'http://localhost:8000/search?q=Anker'                         # exact brand
curl 'http://localhost:8000/search?q=Schokolade&require_tags=vegan' # dietary filter
curl 'http://localhost:8000/search?q=günstige%20Windeln&sort=price_low'
```

`make help` lists all targets; OpenAPI docs are at `http://localhost:8000/docs`. The API listens on
`localhost:8000`, Postgres on `localhost:5433`.

---

## Evaluation & strategy configuration

The embedder, filter, and ranker are interfaces selected by environment variable:

| Concern | Env var | Default | Options |
|---|---|---|---|
| Agent LLM | `LLM_MODEL` | `openai/gpt-4o-mini` | any LiteLLM model id (`vertex_ai/…`, `anthropic/…`, …) |
| Embedder | `EMBEDDING_PROVIDER` | `local` | `local`, `vertex`, `openai` |
| Vector backend | `RETRIEVER_BACKEND` | `pgvector` | `pgvector` |
| Candidate filter | `FILTER_STRATEGY` | `absolute` | `absolute`, `autocut`, `relative`, `none` |
| Ranker | `RANKING_STRATEGY` | `constrained` | `constrained`, `mmr`, `zscore` |

```bash
FILTER_STRATEGY=autocut RANKING_STRATEGY=mmr   # swap a strategy without code changes
```

`make eval` runs labelled queries (`data/eval_queries.json`) through every filter × ranker combination
and reports nDCG, Recall, and MRR via [`ranx`](https://github.com/AmenRa/ranx). It is the mechanism for
choosing a strategy or re-tuning the filter ceiling for a new embedding model.

```bash
make eval
```

`ranx` is dev-only and never runs in the request path (RRF there is a few lines; see
[ADR 0001](docs/decisions/0001-hybrid-retrieval-with-rrf.md)). On this small catalog the absolute scores
are illustrative; the relative ordering of strategies is the useful signal. All settings:
[.env.example](.env.example).

---

## Project structure

```
apps/
  backend/
    app/
      main.py            FastAPI app: /search, /health, /ready
      config.py          typed settings (env-driven)
      db/                ORM models, async session, init.sql (schema + indexes)
      embeddings/        Embedder ABC + local / Vertex / OpenAI + factory
      retrieval/
        pgvector.py      hybrid retriever (semantic + keyword + fuse + rank)
        fusion.py        Reciprocal Rank Fusion
        filtering/       CandidateFilter ABC + 4 strategies + factory
        ranking/         Ranker ABC + 3 strategies + factory
    data/
      adapters/          one adapter per partner (raw feed → canonical)
      catalogs/          committed dm / edeka / amazon snapshots
      seed.py            load catalogs → DB
      embed.py           compute embeddings (provenance-aware, idempotent)
      eval.py            A/B evaluation harness (make eval)
    tests/               unit + DB-backed + agent tests
  frontend/              optional chat UI (future)
demo/                    5-query demo client (make demo)
docs/
  architecture.md        system + query-path diagrams
  decisions/             ADRs 0001–0006
docker-compose.dev.yml   dev stack (API + Postgres/pgvector)
Makefile                 up / seed / embed / eval / demo / test / lint
```

---

## Tech stack

- FastAPI, async SQLAlchemy 2.0, asyncpg
- PostgreSQL + pgvector — HNSW cosine index and a German `tsvector` in one database
- sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`, 384-d), baked in for offline use;
  Vertex AI / OpenAI swappable
- Babel (prices) and Pint (units) for ingestion
- uv (dependencies), ruff (lint), pytest + pytest-asyncio (tests)
- Docker for all commands

---

## Testing

`make test` runs 96 tests. The behavioural ones cover the cases specific to this problem:

- cross-lingual retrieval (English `pasta dinner` finds German Spaghetti; the keyword arm returns nothing
  for it, so the hybrid is doing real work)
- cross-partner fairness (a flooding partner is capped; a lone weak item is not promoted — a regression
  test for the per-partner-normalization bug)
- price-per-unit ordering (`sort=price_low` compares like units only, re-orders the relevant set)
- empty results when nothing matches, rather than noise

---

## Deployment

Runs on Docker locally. The GCP path follows from the existing interfaces:

- **Cloud Run** serves the FastAPI container (the production `Dockerfile` is multi-stage, non-root).
- **Vertex AI** embeddings via `EMBEDDING_PROVIDER=vertex`, moving inference off the request host.
- **Vector store** stays Postgres + pgvector (Cloud SQL); a warehouse backend such as BigQuery is the
  documented scale path behind the `Retriever` interface
  ([ADR 0003](docs/decisions/0003-pgvector-with-retriever-interface.md)).

Provisioning (Terraform, CI/CD) is Task 3.

---

## Limitations

- **Cross-lingual coverage is uneven.** The local model maps many English↔German pairs (`pasta dinner` →
  Spaghetti, `coffee` → Kaffee) but not all (`diaper` does not map to *Windeln*). German queries always
  work. Query normalization belongs to the Task-2 agent, or a larger/cloud embedder via config.
- **Small catalog** (~145 products). Enough to show the cross-catalog behaviour; the filter ceiling is
  calibrated on a small labelled set and should be re-derived (`make eval`) for a larger corpus.

---

## License

MIT — see [LICENSE](LICENSE).
