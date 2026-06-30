"""The hybrid retriever — the retrieval pipeline shared by every backend.

One query runs two arms and fuses them: a **semantic arm** (a pluggable
:class:`~app.retrieval.vector_index.VectorIndex` — pgvector locally/AWS, BigQuery on GCP) and a
**lexical arm** (Postgres German full-text, always). Reciprocal Rank Fusion merges the two rankings,
the rows are hydrated from Postgres (the catalog's source of truth), and a pluggable ``Ranker``
produces the final order. Only the vector index varies by deployment; this orchestration does not,
so it lives here once rather than being duplicated per backend.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from app.config import get_settings
from app.db.session import SessionFactory
from app.embeddings import Embedder
from app.retrieval._rows import load_candidates, to_hit
from app.retrieval.base import Retriever
from app.retrieval.filtering import CandidateFilter, get_candidate_filter
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.pgvector import fulltext_candidates
from app.retrieval.ranking import Ranker, get_ranker
from app.retrieval.session import SessionProvider
from app.retrieval.types import RetrievalCapability, SearchHit, Sort
from app.retrieval.vector_index import VectorIndex
from app.shared.partner import PartnerSlug


class HybridRetriever(Retriever):
    """Semantic (``VectorIndex``) + German lexical (Postgres), fused by RRF, then ranked."""

    def __init__(
        self,
        embedder: Embedder,
        vector_index: VectorIndex,
        ranker: Ranker | None = None,
        candidate_filter: CandidateFilter | None = None,
        *,
        fulltext_min_rank: float = 0.0,
        session_provider: SessionProvider | None = None,
    ) -> None:
        self._embedder = embedder
        self._vector_index = vector_index
        self._ranker = ranker or get_ranker()
        self._filter = candidate_filter or get_candidate_filter(ceiling=get_settings().filter_ceiling)
        self._fulltext_min_rank = fulltext_min_rank
        # The retriever owns its Postgres access (lexical arm + row hydration, and the pgvector
        # semantic arm when that's the index): a provider yields a fresh session per search.
        self._session_provider = session_provider or SessionFactory

    @property
    def capabilities(self) -> frozenset[RetrievalCapability]:
        # Hybrid on every backend: the semantic arm is the configured VectorIndex, the lexical arm
        # is always Postgres German full-text. So both arms are present regardless of vector store.
        return frozenset({RetrievalCapability.VECTOR, RetrievalCapability.FULLTEXT})

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        partner: PartnerSlug | None = None,
        sort: Sort = Sort.RELEVANCE,
        require_tags: Sequence[str] | None = None,
        candidate_k: int = 50,
    ) -> list[SearchHit]:
        # ``embed_query`` is a blocking network call into the embeddings SDK; offload it to a thread
        # so the embedding round-trip doesn't stall the event loop for every other request.
        query_vector = await asyncio.to_thread(self._embedder.embed_query, query)
        filters = {"partner": partner, "require_tags": require_tags, "candidate_k": candidate_k}

        async with self._session_provider() as session:
            # Semantic arm: the configured vector store (Postgres or BigQuery). The lexical arm and
            # row hydration are always Postgres, on this same session.
            vector_ids = await self._vector_index.candidates(
                query_vector,
                self._embedder.model_id,
                candidate_filter=self._filter,
                session=session,
                **filters,
            )
            fulltext_ids = await fulltext_candidates(
                session, query, min_rank=self._fulltext_min_rank, **filters
            )

            fused = reciprocal_rank_fusion([vector_ids, fulltext_ids])
            if not fused:
                return []

            candidates, products = await load_candidates(session, fused)

        ranked_ids = self._ranker.rank(candidates, top_k=top_k, sort=sort)
        # An id from a remote index but missing in Postgres (mid re-embed) is skipped, not fatal.
        return [to_hit(products[pid], fused[pid]) for pid in ranked_ids if pid in products]
