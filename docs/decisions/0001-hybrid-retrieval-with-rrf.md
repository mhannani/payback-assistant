# 0001 — Hybrid retrieval (vector + full-text) fused with Reciprocal Rank Fusion

**Status:** Accepted · **Date:** 2026-06-27

## Context

The assistant must match products by **meaning** (a German or English query like
"pasta dinner" should find spaghetti) *and* by **exact keywords** (a brand like "Anker",
or "Windeln"). Neither alone is sufficient:

- **Vector search alone** misses exact lexical matches and is weaker on rare brand tokens.
- **Full-text alone** is brittle across languages — verified empirically: the German
  full-text index returns **0 results** for the English phrase "pasta dinner".

## Decision

Run **two arms** and fuse them:

1. **Semantic arm** — pgvector cosine similarity (HNSW index) over multilingual
   sentence-transformer embeddings. Handles meaning and cross-lingual matching.
2. **Keyword arm** — Postgres German full-text (`tsvector` / `ts_rank` /
   `websearch_to_tsquery`). Handles exact terms, brands, and German stemming
   ("Windeln" → "Windel").

Fuse the two ranked lists with **Reciprocal Rank Fusion (RRF, k=60)**:
`score(d) = Σ 1/(k + rank_i(d))`.

## Why RRF (and why not just add the scores)

The two arms produce **incomparable scores** — cosine distance vs. `ts_rank`. Adding or
averaging them directly is meaningless. RRF fuses on **rank, not raw score**, so the
scales never need reconciling, and items that rank well in *both* arms accumulate the most
(agreement is rewarded). `k=60` is the original published default (Cormack et al., 2009),
robust across benchmarks and the default in Milvus, Azure AI Search, and others.

We implement RRF directly (≈ one line) rather than depending on an IR library such as
`ranx`: that library is built for offline evaluation/benchmarking over TREC files and pulls
in a heavy JIT dependency, which is the wrong tool inside a latency-sensitive request path.

## Consequences

- Fusion is rank-based, so it avoids the score-normalization fragility that later bites the
  ranking layer (see [0002](0002-fair-cross-partner-ranking.md)).
- Fusion operates on id lists only (no SQL), so it is reused unchanged by any backend.
- Both arms are weighted equally. Per-arm weighting (e.g. leaning on the semantic arm for a
  vague query) is a deliberate non-feature here: it only earns its place alongside a real
  query-confidence signal to set the weights, which belongs to the intent agent (Task 2),
  not the retriever. We will add it there rather than ship an unused knob now.

## References

- Cormack, Clarke, Buettcher, *Reciprocal Rank Fusion outperforms Condorcet…*, SIGIR 2009.
- OpenSearch, *Introducing reciprocal rank fusion for hybrid search*:
  <https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/>
- pgvector SQLAlchemy distance operators (`cosine_distance`):
  <https://github.com/pgvector/pgvector-python>
- PostgreSQL full-text search (`websearch_to_tsquery`, `ts_rank`):
  <https://www.postgresql.org/docs/current/textsearch-controls.html>
