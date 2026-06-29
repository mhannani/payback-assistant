"""pgvector hybrid retriever.

Searches the catalog two ways and fuses the rankings: a semantic arm (vector cosine
similarity over the embeddings) and a keyword arm (Postgres German full-text). The
two arms are built and tested as separate helpers first, then wired into
``PgVectorRetriever`` — each piece is independently verifiable.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, Text, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import Product
from app.embeddings import Embedder
from app.retrieval.base import Retriever
from app.retrieval.filtering import CandidateFilter, ScoredCandidate, get_candidate_filter
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.ranking import Ranker, get_ranker
from app.retrieval.types import Candidate, SearchHit, Sort
from app.shared.partner import PartnerSlug


def _apply_filters(
    stmt: Select,
    *,
    partner: PartnerSlug | None,
    require_tags: Sequence[str] | None,
) -> Select:
    """Add the optional partner / tag filters shared by both search arms.

    ``require_tags`` uses the array-contains (``@>``) operator, served by the GIN
    index on ``tags``, so a product must carry every requested tag. The literal is
    cast to ``text[]`` to match the column type (the default ``varchar[]`` bind has
    no ``@>`` operator against a ``text[]`` column).
    """
    if partner is not None:
        stmt = stmt.where(Product.partner.has(slug=partner.value))
    if require_tags:
        stmt = stmt.where(Product.tags.contains(cast(list(require_tags), ARRAY(Text))))
    return stmt


async def vector_candidates(
    session: AsyncSession,
    query_vector: Sequence[float],
    model_id: str,
    *,
    candidate_filter: CandidateFilter,
    partner: PartnerSlug | None = None,
    require_tags: Sequence[str] | None = None,
    candidate_k: int = 50,
) -> list[uuid.UUID]:
    """Return relevant product ids ranked by semantic (cosine) closeness to the query.

    Only embeddings produced by ``model_id`` are considered — vectors from different
    models live in different spaces and must never be compared. Ordering by
    ``cosine_distance`` uses the HNSW index for fast approximate nearest neighbours.

    ANN always returns the nearest ``candidate_k`` even when most are irrelevant, so the
    raw distance is run through ``candidate_filter`` here (pre-fusion, on the un-compressed
    distance) to drop the noise tail before fusion and ranking ever see it.
    """
    distance = Product.embedding.cosine_distance(query_vector)
    stmt = (
        select(Product.id, distance.label("distance"))
        .where(
            Product.embedding.is_not(None),
            Product.embedding_model == model_id,
        )
        .order_by(distance)
        .limit(candidate_k)
    )
    stmt = _apply_filters(stmt, partner=partner, require_tags=require_tags)
    rows = (await session.execute(stmt)).all()
    scored = [ScoredCandidate(product_id=row.id, distance=row.distance) for row in rows]
    return [c.product_id for c in candidate_filter.filter(scored)]


async def fulltext_candidates(
    session: AsyncSession,
    query: str,
    *,
    partner: PartnerSlug | None = None,
    require_tags: Sequence[str] | None = None,
    candidate_k: int = 50,
    min_rank: float = 0.0,
) -> list[uuid.UUID]:
    """Return product ids ranked by German full-text relevance to the query.

    Complements the semantic arm: it catches exact terms and brand names ("Anker",
    "Windeln") the embedding can blur. ``websearch_to_tsquery`` parses raw user input
    safely (no operator syntax required); the ``german`` config stems both sides so
    "Windeln" matches "Windel". ``@@`` is served by the GIN index on ``search_tsv``.

    This arm's relevance gate (the analogue of the vector arm's CandidateFilter): the ``@@``
    match plus an optional ``ts_rank >= min_rank`` floor. ``websearch_to_tsquery`` AND-joins
    terms, so a row must already contain every stem to match; the floor additionally trims
    the graded ts_rank tail of barely-relevant matches so it doesn't feed fusion the noise
    the vector arm's ceiling drops on its side.
    """
    tsquery = func.websearch_to_tsquery("german", query)
    rank = func.ts_rank(Product.search_tsv, tsquery)
    stmt = select(Product.id).where(Product.search_tsv.bool_op("@@")(tsquery))
    if min_rank > 0.0:
        stmt = stmt.where(rank >= min_rank)
    stmt = stmt.order_by(rank.desc()).limit(candidate_k)
    stmt = _apply_filters(stmt, partner=partner, require_tags=require_tags)
    return list((await session.scalars(stmt)).all())


class PgVectorRetriever(Retriever):
    """Hybrid retriever over Postgres + pgvector.

    Composes the tested pieces: embed the query, run the semantic and keyword arms, fuse
    with RRF, then hand the candidates to a ``Ranker`` for the final order. The arms, the
    fusion, and the ranking are each verified on their own; this class only wires them.
    The ranker is injected, so the ranking strategy is a swappable, A/B-testable choice.
    """

    def __init__(
        self,
        embedder: Embedder,
        ranker: Ranker | None = None,
        candidate_filter: CandidateFilter | None = None,
        *,
        fulltext_min_rank: float = 0.0,
    ) -> None:
        self._embedder = embedder
        self._ranker = ranker or get_ranker()
        # When no filter is injected, build the configured default (ceiling from settings — the
        # single source of truth for the calibrated value).
        self._filter = candidate_filter or get_candidate_filter(ceiling=get_settings().filter_ceiling)
        self._fulltext_min_rank = fulltext_min_rank

    async def search(
        self,
        session: AsyncSession,
        query: str,
        *,
        top_k: int = 10,
        partner: PartnerSlug | None = None,
        sort: Sort = Sort.RELEVANCE,
        require_tags: Sequence[str] | None = None,
        candidate_k: int = 50,
    ) -> list[SearchHit]:
        # Embed once, up front (the embedder is synchronous).
        query_vector = self._embedder.embed_query(query)
        filters = {"partner": partner, "require_tags": require_tags, "candidate_k": candidate_k}

        # The two arms run sequentially: a single AsyncSession is not safe for
        # concurrent queries, and each arm is a fast indexed lookup, so the
        # back-to-back cost is negligible — not worth a second connection here.
        vector_ids = await vector_candidates(
            session,
            query_vector,
            self._embedder.model_id,
            candidate_filter=self._filter,
            **filters,
        )
        fulltext_ids = await fulltext_candidates(
            session, query, min_rank=self._fulltext_min_rank, **filters
        )

        fused = reciprocal_rank_fusion([vector_ids, fulltext_ids])
        if not fused:
            return []

        candidates, products = await self._load_candidates(session, fused)
        ranked_ids = self._ranker.rank(candidates, top_k=top_k, sort=sort)
        return [_to_hit(products[pid], fused[pid]) for pid in ranked_ids]

    async def _load_candidates(
        self, session: AsyncSession, fused: dict[uuid.UUID, float]
    ) -> tuple[list[Candidate], dict[uuid.UUID, Product]]:
        """Load the fused products once, eager-loading the partner relationship.

        Eager-loading avoids a lazy relationship access later (which would attempt async
        IO outside the await context and fail). Returns the ranking ``Candidate`` views
        plus the full rows, keyed by id, for building the final hits.
        """
        stmt = (
            select(Product)
            .where(Product.id.in_(fused.keys()))
            .options(selectinload(Product.partner), selectinload(Product.brand))
        )
        products = {p.id: p for p in (await session.scalars(stmt)).all()}
        candidates = [
            Candidate(
                product_id=p.id,
                partner=PartnerSlug(p.partner.slug),
                fused_score=fused[p.id],
                price_cents=p.price_cents,
                weight_g=p.weight_g,
                volume_ml=p.volume_ml,
            )
            for p in products.values()
        ]
        return candidates, products


def _to_hit(product: Product, score: float) -> SearchHit:
    """Build the public ``SearchHit`` from a loaded product row and its final score."""
    return SearchHit(
        product_id=product.id,
        partner=PartnerSlug(product.partner.slug),
        name=product.name,
        brand=product.brand.name if product.brand else None,
        description=product.description,
        price_cents=product.price_cents,
        currency=product.currency,
        image_url=product.image_url,
        tags=list(product.tags),
        weight_g=product.weight_g,
        volume_ml=product.volume_ml,
        score=score,
        attrs=dict(product.attrs),
    )
