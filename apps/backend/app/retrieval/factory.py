"""Build the configured retriever.

One place assembles the retrieval stack from settings — the vector backend, the candidate
filter, and the ranker — so each is a config choice and the API depends only on the
``Retriever`` interface. Only ``pgvector`` exists today; this factory is the seam a
warehouse backend (e.g. BigQuery) would later plug into.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.embeddings import Embedder, get_embedder
from app.retrieval.base import Retriever
from app.retrieval.filtering import get_candidate_filter
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.ranking import get_ranker
from app.retrieval.vector_index import BigQueryVectorIndex, PgVectorIndex, VectorIndex


@lru_cache
def get_cached_retriever() -> Retriever:
    """The process-wide retriever, built once from config.

    Both the /search endpoint and the agent's search node use this, so the embedding client (and
    its model/SDK init) is created a single time per process rather than per request/turn.
    """
    return get_retriever()


def _vector_index(s: Settings, embedder: Embedder) -> VectorIndex:
    """The semantic-search index for the configured backend — the only part that varies."""
    match s.retriever_backend:
        case "pgvector":
            return PgVectorIndex()
        case "bigquery":
            # Fail fast if the GCP prerequisite is unset, the way the embedder factory validates
            # before serving rather than 500-ing on first query.
            if not s.vertexai_project:
                raise ValueError(
                    "retriever_backend=bigquery requires VERTEXAI_PROJECT (the GCP project) to be set."
                )
            return BigQueryVectorIndex(s, embedder)
        case other:
            raise ValueError(
                f"unknown retriever_backend {other!r}; expected pgvector or bigquery"
            )


def get_retriever(
    embedder: Embedder | None = None, settings: Settings | None = None
) -> Retriever:
    """Assemble the hybrid retriever with the configured vector index, filter, and ranker."""
    s = settings or get_settings()
    embedder = embedder or get_embedder(s)
    return HybridRetriever(
        embedder,
        _vector_index(s, embedder),
        ranker=get_ranker(s.ranking_strategy),
        candidate_filter=get_candidate_filter(s.filter_strategy, ceiling=s.filter_ceiling),
        fulltext_min_rank=s.fulltext_min_rank,
    )
