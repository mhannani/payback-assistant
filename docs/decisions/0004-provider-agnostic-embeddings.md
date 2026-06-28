# 0004 — Provider-agnostic embeddings: local default, cloud-swappable

**Status:** Accepted · **Date:** 2026-06-27

## Context

The assistant needs text embeddings to power semantic search across German and English
queries. The deliverable must **run offline** for a reviewer (`make up`, no credentials),
while production on GCP would likely serve embeddings from **Vertex AI**. We also want to
avoid hard-wiring a single vendor.

## Decision

An **`Embedder` interface** with the provider chosen by config:

- **`LocalEmbedder` (default):** a multilingual sentence-transformers model
  (`paraphrase-multilingual-MiniLM-L12-v2`, 384-d), baked into the Docker image so it runs
  offline with no credentials and matches German↔English out of the box.
- **`VertexEmbedder` / `OpenAIEmbedder`:** real implementations behind the same interface
  (SDK imported lazily), selected by `embedding_provider` — used in production, not exercised
  in the offline demo.

Two correctness rules live in the contract, not in each impl:
- **Normalization is owned by the base class.** Implementations return raw vectors; the base
  L2-normalizes them, so every provider matches the cosine HNSW index and none can silently
  regress search quality.
- **The factory rejects a dimension mismatch at construction** — a provider whose vectors
  don't fit the fixed `Vector(384)` column fails loudly at startup, not mid-embed.

Each product also records **which model produced its vector** (`embedding_model`), so the
embed step re-embeds when the provider changes and retrieval rejects a stale-model mismatch
(vectors from different models are not comparable).

## Why this design

- **Runnable + production-aligned:** local-default keeps the demo offline; Vertex is a
  config flip for production — honouring the GCP preference without breaking the demo, and
  without vendor lock-in.
- **Cold-start note (for deployment):** the local model pulls in torch (~heavy image). In
  production, flipping to Vertex moves inference off the API container, which is exactly why
  the brief separates "Vertex for model serving" from "Cloud Run for the API"; making the
  local deps an optional group keeps the production image lean.

## Consequences

- Switching providers is a config change (+ re-embed), guarded so it can't silently corrupt
  search.
- MiniLM-384 is a deliberate cost/latency/offline choice for a lightweight assistant; a
  larger model is a tunable, at the cost of image size and latency.

## References

- pgvector cosine / HNSW: <https://github.com/pgvector/pgvector>
- sentence-transformers multilingual models: <https://www.sbert.net/docs/pretrained_models.html>
- Vertex AI text embeddings: <https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings>
