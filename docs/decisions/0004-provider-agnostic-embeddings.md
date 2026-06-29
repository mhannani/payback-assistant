# 0004 — Provider-agnostic embeddings: managed cloud providers

**Status:** Accepted · **Date:** 2026-06-27 (revised 2026-06-29)

## Context

The assistant needs text embeddings to power semantic search across German and English queries.
Production on GCP would serve embeddings from **Vertex AI**; we also want to avoid hard-wiring a
single vendor. Embedding is therefore treated as a managed-provider call, not an in-process model —
which matches how embeddings are served at scale (a managed API or a dedicated serving tier, not a
model bundled into the API container).

## Decision

An **`Embedder` interface** with the provider chosen by config (`embedding_provider`):

- **`OpenAIEmbedder` (default):** `text-embedding-3-small` (1536-d).
- **`VertexEmbedder`:** `text-multilingual-embedding-002` (768-d), the GCP-native option.

Both are thin SDK adapters (the SDK is imported lazily, so only the configured client initializes).
There is no in-process model and no torch in the image — inference is served off-host, which keeps
the production image small and cold starts fast, and is why the brief separates "Vertex for model
serving" from "Cloud Run for the API".

Two correctness rules live in the contract, not in each impl:
- **Normalization is owned by the base class.** Implementations return raw vectors; the base
  L2-normalizes them, so every provider matches the cosine HNSW index and none can silently
  regress search quality.
- **The factory rejects a dimension mismatch at construction** — a provider whose vectors don't
  match the declared `EMBEDDING_DIM` fails loudly at startup, not mid-embed.

**One declared dimension.** `EMBEDDING_DIM` (config) sizes the `embedding` column — applied by
`data.init_db`, which substitutes it into `db/init.sql` — and the ORM column, with the factory
guard enforcing it against the active provider. No dimension is hardcoded or duplicated.

Each product records **which model produced its vector** (`embedding_model`), so the embed step
re-embeds when the provider changes and retrieval rejects a stale-model mismatch (vectors from
different models are not comparable).

## Why this design

- **Production-aligned, no lock-in:** swapping OpenAI ↔ Vertex is a config change (+ a re-embed and
  a matching `EMBEDDING_DIM`), guarded so it can't silently corrupt search.
- **Lean image:** no model weights or torch to ship, so the production image stays small and starts
  fast — the cost is that a key/credentials are required (there is no offline fallback).

## Consequences

- The service requires a provider key; there is no zero-credential mode.
- The `absolute` filter ceiling is bound to the active model's cosine-distance scale and is
  re-derived (`make eval`) when the provider changes — see
  [0002](0002-fair-cross-partner-ranking.md) / the filter docs.

## References

- pgvector cosine / HNSW: <https://github.com/pgvector/pgvector>
- OpenAI embeddings: <https://platform.openai.com/docs/guides/embeddings>
- Vertex AI text embeddings: <https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings>
