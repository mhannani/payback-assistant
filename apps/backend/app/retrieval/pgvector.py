"""Postgres retrieval arms — the SQL building blocks of hybrid search.

Two independent, tested helpers: ``vector_candidates`` (pgvector cosine over the HNSW index) and
``fulltext_candidates`` (German full-text via ``tsvector``/``ts_rank``).
:class:`~app.retrieval.hybrid.HybridRetriever` composes them — ``PgVectorIndex`` wraps
``vector_candidates`` as the local/AWS semantic arm, and the lexical arm runs ``fulltext_candidates``
on every backend.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, Text, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product
from app.retrieval.filtering import CandidateFilter, ScoredCandidate
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

