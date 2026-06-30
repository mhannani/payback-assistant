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
from app.retrieval.pgvector import PgVectorRetriever
from app.retrieval.ranking import get_ranker


@lru_cache
def get_cached_retriever() -> Retriever:
    """The process-wide retriever, built once from config.

    Both the /search endpoint and the agent's search node use this, so the embedding client (and
    its model/SDK init) is created a single time per process rather than per request/turn.
    """
    return get_retriever()


def get_retriever(
    embedder: Embedder | None = None, settings: Settings | None = None
) -> Retriever:
    """Assemble the retriever named by ``retriever_backend`` with its filter and ranker."""
    s = settings or get_settings()
    embedder = embedder or get_embedder(s)
    candidate_filter = get_candidate_filter(s.filter_strategy, ceiling=s.filter_ceiling)
    ranker = get_ranker(s.ranking_strategy)

    match s.retriever_backend:
        case "pgvector":
            return PgVectorRetriever(
                embedder,
                ranker=ranker,
                candidate_filter=candidate_filter,
                fulltext_min_rank=s.fulltext_min_rank,
            )
        case other:
            raise ValueError(f"unknown retriever_backend {other!r}; expected pgvector")
