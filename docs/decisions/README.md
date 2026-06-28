# Architecture Decision Records

Each record captures one decision: the context, the options weighed, the choice, and
its consequences — with references where external sources informed it.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-hybrid-retrieval-with-rrf.md) | Hybrid retrieval (vector + full-text) fused with Reciprocal Rank Fusion | Accepted |
| [0002](0002-fair-cross-partner-ranking.md) | Fair cross-partner ranking via constrained re-ranking, not per-source normalization | Accepted |
| [0003](0003-pgvector-with-retriever-interface.md) | pgvector for the demo behind a `Retriever` interface; BigQuery as the documented production path | Accepted |
| [0004](0004-provider-agnostic-embeddings.md) | Provider-agnostic embeddings (local default, Vertex/OpenAI swappable) | Accepted |
| [0005](0005-candidate-filtering.md) | Candidate filtering: cut the vector noise tail before fusion (absolute distance ceiling) | Accepted |
