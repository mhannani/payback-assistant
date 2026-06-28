# Architecture

How the three disparate partner catalogs (dm, EDEKA, Amazon) are **ingested, indexed, and queried
simultaneously** — the Task-1 recommendation engine in full.

There are two paths: an **offline ingestion path** (run once, by `make seed && make embed`) that turns
three messy feeds into one searchable catalog, and an **online query path** (every `/search` request)
that retrieves across all of them. The diagrams below show each in detail. They are plain text, so
they render in any Markdown viewer.

---

## 1. The whole system at a glance

```text
  PARTNER FEEDS                INGESTION (offline)              QUERY PATH (online)
  (disparate)                  make seed + make embed           GET /search

  ┌──────────┐                 ┌────────────────────┐
  │ dm.json  │──┐              │ Partner adapters   │          ┌─────────────────────────┐
  ├──────────┤  │   raw        │  Babel → cents     │          │ client / curl /         │
  │edeka.json│──┼──────────▶   │  Pint  → g · ml    │          │ client / intent agent   │
  ├──────────┤  │   records    │  labels → tags[]   │          └────────────┬────────────┘
  │amazon.jsn│──┘              └─────────┬──────────┘                       │
  └──────────┘                           │ canonical Product               ▼
                                         ▼                       ┌─────────────────────────┐
                              ┌──────────────────────┐           │ FastAPI  /search        │
                              │ PostgreSQL + pgvector │◀─────────▶│ PgVectorRetriever       │
                              │ products + 4 indexes  │  lookups  │ (embed→arms→fuse→rank)  │
                              └──────────┬───────────┘           └────────────┬────────────┘
                                         ▲                                    │
                              make embed │ 384-d vector + provenance          ▼
                                         │                          list[ProductOut] → client
```

The valuable property: **everything expensive happens at ingestion**, so a request is just index
lookups + vector math. The three feeds never leak their differences past the adapter layer.

---

## 2. Ingestion path — three feeds → one canonical catalog

Each partner has its own adapter (a `PartnerAdapter` ABC + one concrete class each, chosen by a
registry). The adapter is the *only* place that knows a partner's quirks.

```text
  RAW record (per partner)            normalize.py helpers              CANONICAL Product
                                                                        (one shape, all partners)
  dm:  price_eur 4.26       ──▶  euros_to_cents / german_price_   ──▶   partner
       pack_size "500 g"          to_cents  (Babel, locale-aware:        brand · name
       labels ["en:organic"]      "12,30" → 1230)                       price_cents : int
                                                                        weight_g / volume_ml : int?
                          ──▶  parse_quantity  (Pint:           ──▶    tags : text[]
                               "1,5 l" → 1500 ml, "500 g" → 500 g)      description  (→ embedded)
                                                                        attrs : jsonb
                          ──▶  normalize_tags  (strip "en:",    ──▶    (asin · rating · gtin …)
                               keep curated dietary set)

                          ──▶  compose_description (brand·name·size)
```

**The rule that decides where each field goes:** if it can be *mathematically compared* (price, size)
or *strictly filtered* (tags, partner) → a **typed column**; if it's subjective/descriptive → into
`description`, which gets embedded; partner-specific extras (asin, rating, gtin) → opaque `attrs` JSONB.

---

## 3. The canonical schema & its four indexes

One `products` table backs **both** retrieval arms plus filtering — no separate search service.

```text
  products
  ├─ id · partner_id · brand_id
  ├─ name · description · price_cents · currency · image_url
  ├─ tags        TEXT[]          ──────▶  GIN index        →  require_tags filter
  ├─ weight_g · volume_ml        (typed columns)           →  price-per-unit sort
  ├─ embedding   VECTOR(384)     ──────▶  HNSW (cosine)     →  SEMANTIC arm
  ├─ embedding_model             (provenance: which model produced the vector)
  ├─ search_tsv  TSVECTOR        ──────▶  GIN index         →  KEYWORD arm
  │              (generated, German, always in sync with name+description)
  └─ attrs       JSONB           ──────▶  GIN index         →  partner-specific lookups
```

`embedding_model` records *which* model produced each vector, so a provider switch re-embeds only the
stale rows (`make embed` is idempotent and provenance-driven). `search_tsv` is a database-generated
column, so the German full-text vector can never drift out of sync with `name`/`description`.

---

## 4. The embedding layer (provider-agnostic)

```text
  text (product description / query)
        │
        ▼
  ┌──────────────────────────────────────────────────────────┐
  │ Embedder (ABC)                                            │
  │   embed_texts() ── L2-normalize  (owned by the base)      │
  │        ├── LocalEmbedder   MiniLM multilingual · 384-d ·  │   ← EMBEDDING_PROVIDER
  │        │                   offline  (default)            │
  │        ├── VertexEmbedder  768-d                          │
  │        └── OpenAIEmbedder  1536-d                         │
  └───────────────────────┬──────────────────────────────────┘
                          ▼
              factory dimension guard
              (reject at startup if ≠ schema's 384-d)
                          │
                          ▼
              unit vector → products.embedding
```

L2-normalization lives in the **base contract**, so no provider can forget it and silently degrade the
cosine index. The factory fails *loudly at startup* if a provider's dimension doesn't match the schema —
never silent garbage.

---

## 5. Query path — the hybrid retrieval pipeline (the heart of Task 1)

This is what runs on every `GET /search`. Two arms, each gated by the relevance discipline appropriate
to its score scale, fused by RRF, then a pluggable fair ranker.

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
              │  rank-based → arms' scales never compared  │
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

**Why each piece exists** (full reasoning in [decisions/](decisions/)):

| Stage | What it does | Why it's there |
|---|---|---|
| Two arms | semantic (meaning, cross-lingual) + keyword (exact terms, brands, German stemming) | neither alone suffices — German FT returns 0 for English `pasta dinner`; the vector arm blurs exact brands like `Anker` ([ADR 0001](decisions/0001-hybrid-retrieval-with-rrf.md)) |
| CandidateFilter | drops the ANN noise tail on raw cosine distance, pre-fusion | ANN always returns the nearest N even when irrelevant → honest "nothing" instead of shower gel ([ADR 0005](decisions/0005-candidate-filtering.md)) |
| ts_rank floor | the keyword arm's relevance gate (its score has no comparable scale to cosine) | keeps the two arms symmetric in quality before fusion |
| RRF | merges the two ranked lists on **rank, not raw score** | the arms' scales (cosine vs ts_rank) are incomparable; agreement is rewarded ([ADR 0001](decisions/0001-hybrid-retrieval-with-rrf.md)) |
| Ranker | final order: relevance first, then a bounded per-partner cap | a dense catalog must not crowd the others out; a lone weak item must not be promoted ([ADR 0002](decisions/0002-fair-cross-partner-ranking.md)) |
| price-per-unit sort | `sort=price_low` re-orders the relevant set by value, comparing like with like | a 1 L @ €2 beats 200 ml @ €0.80; foods/drinks/unitless never interleave |

---

## 6. The intent agent (in front of retrieval)

A LangGraph state machine sits in front of `/search`: it classifies the raw query (LLM, via a
LiteLLM gateway), picks the next action, and returns products, a clarifying question, or a
partner hand-off. Per-conversation state is persisted in Postgres so a paused clarify survives a
restart.

```text
  POST /assist {query}
        │
        ▼
   ┌─────────┐   LLM: with_structured_output(Classification)
   │ classify│   → intent · language · partner · sort · tags · search_query
   └────┬────┘   then decide_action(...)
        │
   ┌────┴───────────────┬─────────────────────────┐
   ▼                    ▼                          ▼
 search               route_to_partner          clarify
 (run retriever)      (deep-link hand-off)       interrupt(question) ──► pause
   │  hits? │ none       │                          │ /assist/resume {thread_id, answer}
   ▼        ▼            ▼                          ▼
 products  clarify     route response            (answer) ──► back to classify
   └────────┴────────────┴──────────────────────────┘
        ▼
  AssistResponse = products | clarify | route   (durable state: AsyncPostgresSaver)
```

The agent only *chooses* the mechanical knobs (partner / sort / tags) and calls the same retriever
the `/search` endpoint uses — retrieval stays a pure primitive (see §5). Full rationale:
[decisions/0006](decisions/0006-intent-agent-langgraph.md).

---

## 7. The seams (where the cloud-deploy task plugs in)

Each pluggable concern is an **interface + concrete impls + a factory** selected by one env var — so a
new strategy, provider, or backend is a new class, never an edit to the pipeline.

```text
  Built (default)                Config-swappable / documented seam        Env var
  ───────────────────────        ──────────────────────────────────       ─────────────────
  Agent LLM: openai/gpt-4o-mini  any LiteLLM model (Vertex, Anthropic…)    LLM_MODEL
  Embedder : Local        ◀───▶  Vertex · OpenAI                           EMBEDDING_PROVIDER
  Retriever: PgVector     ◀───▶  warehouse backend e.g. BigQuery           RETRIEVER_BACKEND
  Filter   : absolute     ◀───▶  autocut · relative · none                 FILTER_STRATEGY
  Ranker   : constrained  ◀───▶  mmr · zscore                              RANKING_STRATEGY
```

Because the strategies are swappable, they're **measurable**: `make eval` scores every *filter ×
ranker* combination with nDCG/Recall/MRR (via `ranx`, offline only) — see the
[README](../README.md#pluggable-strategies--ab-evaluation).
