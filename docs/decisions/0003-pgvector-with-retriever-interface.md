# 0003 — pgvector for the demo behind a `Retriever` interface; BigQuery as the production path

**Status:** Accepted · **Date:** 2026-06-27

## Context

The brief's preferred production stack lists **BigQuery (for vector search)** on GCP. The
deliverable must also **run offline** for a reviewer (`make up`), which BigQuery cannot —
it needs a GCP project, a dataset, and credentials. We need to honour the production
preference *without* breaking the runnable demo.

A second consideration: the hard part of the problem — fair ranking across disparate
catalogs (see [0002](0002-fair-cross-partner-ranking.md)) — is **application logic that
lives above the vector store**. No vector database (pgvector, Qdrant, Milvus, BigQuery)
solves it for you; it must be written regardless of the store.

## Decision

Put retrieval behind a small **`Retriever` interface**:

- **`PgVectorRetriever`** — the one fully-working implementation. Postgres + pgvector runs
  the demo offline with millisecond latency, no credentials, and reuses the Postgres that
  already holds the catalog.
- **BigQuery** is the documented production path behind the *same* interface. The brief
  scopes BigQuery to *vector search* specifically, so the production split is: BigQuery
  returns nearest-neighbour ids; a low-latency store still serves the catalog rows.

The engine-specific part is only **candidate generation** (the SQL). Fusion and the fair
ranking are pure Python operating on id lists and scores, so they are reused unchanged by
any backend — porting to BigQuery rewrites only the two candidate queries
(`cosine_distance` → `VECTOR_SEARCH`, `tsvector` → `SEARCH`).

## Why not Qdrant / Milvus, or BigQuery now

- **Qdrant / Milvus** would add an operational dependency for ~150 products and still not
  solve the fair-ranking problem. pgvector reuses the existing Postgres.
- **BigQuery is a warehouse (OLAP)** — seconds-latency, serverless, no traditional indexes,
  pay-per-scan. It is the right tool for batch embedding and warehouse-scale similarity,
  but not for serving a real-time assistant directly. Implementing it fully now would need
  a live GCP project and break the offline demo, for an *optional* part of the brief.

## Consequences

- The demo is runnable offline; the production preference is honoured as a documented seam.
- The valuable ranking logic is engine-portable by construction.
- Adding BigQuery later is one new class implementing `Retriever`; the API and agent do not
  change.

## References

- BigQuery vector search (`VECTOR_SEARCH`): <https://cloud.google.com/bigquery/docs/vector-search>
- pgvector (HNSW, cosine): <https://github.com/pgvector/pgvector>
