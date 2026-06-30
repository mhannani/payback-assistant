# 0007 — BigQuery as a pluggable vector index (GCP stays fully hybrid)

**Status:** Accepted · **Date:** 2026-06-30

## Context

The brief names **BigQuery for vector search** as the preferred GCP service. ADR 0003 placed it
behind the `Retriever` interface as the documented scale path; this ADR makes it a real, selectable
backend used on GCP, while pgvector serves local and AWS.

Adding it exposed a structural question. Both deployments do the *same* hybrid retrieval — a semantic
arm + a German lexical arm, fused by RRF, hydrated from Postgres, ranked. The **only** thing that
differs is *where the semantic arm runs*: Postgres + pgvector, or BigQuery `VECTOR_SEARCH`. Treating
that as "two retriever classes" would duplicate the whole pipeline; treating BigQuery as "vector
only" would needlessly throw away the keyword arm — which Cloud SQL, present on GCP anyway, can run.

## Decision

**The vector index is the pluggable seam; hybrid retrieval is the invariant.**

- A `VectorIndex` ABC (`app/retrieval/vector_index.py`) abstracts only the semantic arm:
  `PgVectorIndex` (Postgres cosine over HNSW) and `BigQueryVectorIndex` (`VECTOR_SEARCH`, IVF, cosine).
- One `HybridRetriever` (`app/retrieval/hybrid.py`) owns the shared pipeline: embed → the configured
  `VectorIndex` for the semantic arm **+ Postgres German full-text for the lexical arm** → RRF →
  hydrate rows from Postgres → rank. `RETRIEVER_BACKEND` selects which `VectorIndex` is injected.

So **GCP is fully hybrid**, exactly like local/AWS:

| | Semantic arm | Lexical arm (German FT) | Catalog rows | Checkpointer |
|---|---|---|---|---|
| local / AWS | Postgres pgvector | Postgres | Postgres | Postgres |
| **GCP** | **BigQuery VECTOR_SEARCH** | **Cloud SQL (Postgres)** | Cloud SQL | Cloud SQL |

Both backends therefore advertise `capabilities = {VECTOR, FULLTEXT}` (surfaced on `GET /config`);
the difference is *where the semantic arm runs*, not *which arms exist*.

## Why hybrid on GCP, not vector-only

Cloud SQL stays in the GCP stack (catalog rows + the agent checkpointer) and already has the German
full-text index (`db/init.sql`, applied by `init_db`). So the keyword arm — what catches exact
terms/brands the embedding blurs ("Anker", "Windeln") — runs there for free, in the same session the
retriever already opens for row hydration. Dropping it would be a self-inflicted quality loss with
Cloud SQL right there to serve it. (We deliberately do **not** try to reproduce the German lexical
arm *inside* BigQuery: its `SEARCH()` returns a boolean match, not a graded `ts_rank` to fuse, and it
ships no German stemmer — so the lexical arm belongs on Postgres, not BigQuery.)

## Why the data split (BigQuery vectors, Cloud SQL rows)

- **Single source of truth.** Cloud SQL already holds the catalog and the checkpointer; mirroring
  `price_cents`/`tags`/`name` into BigQuery would create a second authority that drifts on any
  price change, plus a sync pipeline for no functional gain.
- **Right tool per job.** BigQuery is OLAP — seconds-latency, pay-per-scan, no point-lookup index. It
  does the warehouse-scale ANN over the embedding column; a `WHERE id IN (...)` on the Cloud SQL
  primary key serves the 50 rows in sub-ms. An id in BigQuery missing from Postgres (briefly, mid
  re-embed) is skipped during hydration, never fatal.

## Consequences

- **Latency.** BigQuery vector search is seconds-scale (Google's guidance ~1–10 s) vs pgvector's
  milliseconds — acceptable for the GCP warehouse tier and *why* pgvector serves the latency-
  sensitive local/AWS deployments. BigQuery is the scale path, not the real-time one.
- **Eval.** Retrieval quality is measured, not asserted — `make eval` runs against both vector
  indexes and reports the nDCG/Recall/MRR delta.
- **Net simplification.** The `VectorIndex` ABC + one `HybridRetriever` replaced two near-identical
  retriever classes; the orchestration now lives once.
- **ADR 0003 correction.** 0003 said adding BigQuery would be "one new class; the API and agent do
  not change." In practice the API and agent got *simpler* — removing the session from the
  `Retriever` interface (so retrievers own their data access) deleted the agent's
  session-through-config plumbing entirely.

## References

- BigQuery vector search: <https://cloud.google.com/bigquery/docs/vector-search>
- BigQuery `SEARCH` / text analyzers (boolean match; no German stemmer):
  <https://cloud.google.com/bigquery/docs/text-analysis-search>
- ADR 0001 (hybrid RRF), ADR 0003 (pgvector + Retriever interface).
