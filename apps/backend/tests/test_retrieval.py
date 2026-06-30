"""DB-backed retrieval tests against the seeded + embedded catalog.

These run real SQL: pgvector cosine search and Postgres German full-text. They assume
the catalog is seeded and embedded (`make seed && make embed`).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.db.models import Product
from app.retrieval.filtering.none import NoFilter
from app.retrieval.pgvector import fulltext_candidates, vector_candidates
from app.retrieval.types import Sort
from app.shared.partner import PartnerSlug

pytestmark = pytest.mark.usefixtures("embedder")

# These tests exercise the raw vector arm; the cutoff has its own tests in test_filtering.
_NO_FILTER = NoFilter()


async def _names(db_session, ids) -> list[str]:
    return [(await db_session.get(Product, pid)).name for pid in ids]


async def test_vector_candidates_match_meaning_cross_lingual(db_session, embedder) -> None:
    # English query, German catalog: only the semantic arm can bridge this.
    qv = embedder.embed_query("pasta dinner")
    ids = await vector_candidates(
        db_session, qv, embedder.model_id, candidate_filter=_NO_FILTER, candidate_k=5
    )
    names = await _names(db_session, ids)
    assert ids, "expected semantic candidates"
    assert any("spaghetti" in n.lower() or "pasta" in n.lower() for n in names)


async def test_vector_candidates_partner_filter(db_session, embedder) -> None:
    from app.db.models import Partner

    dm_id = (
        await db_session.scalars(select(Partner.id).where(Partner.slug == PartnerSlug.DM.value))
    ).one()
    qv = embedder.embed_query("shampoo")
    ids = await vector_candidates(
        db_session,
        qv,
        embedder.model_id,
        candidate_filter=_NO_FILTER,
        partner=PartnerSlug.DM,
        candidate_k=5,
    )
    assert ids
    for pid in ids:
        # Compare the FK directly — avoids lazy-loading the partner relationship
        # (which would trigger async IO outside the await context).
        product = await db_session.get(Product, pid)
        assert product.partner_id == dm_id


async def test_vector_candidates_require_tags(db_session, embedder) -> None:
    qv = embedder.embed_query("pasta")
    ids = await vector_candidates(
        db_session,
        qv,
        embedder.model_id,
        candidate_filter=_NO_FILTER,
        require_tags=["organic"],
        candidate_k=5,
    )
    assert ids, "expected organic candidates"
    for pid in ids:
        product = await db_session.get(Product, pid)
        assert "organic" in product.tags


async def test_vector_candidates_ignore_other_models(db_session, embedder) -> None:
    # A model_id that produced nothing yields no candidates (provenance guard).
    qv = embedder.embed_query("shampoo")
    ids = await vector_candidates(
        db_session, qv, "nonexistent:model", candidate_filter=_NO_FILTER, candidate_k=5
    )
    assert ids == []


# ── Full-text (keyword) arm ─────────────────────────────────────────────────


async def test_fulltext_german_stemming(db_session) -> None:
    # "Windeln" (plural) must match products titled "Windel" — German stemming.
    ids = await fulltext_candidates(db_session, "Windeln", candidate_k=5)
    names = await _names(db_session, ids)
    assert ids
    assert all("windel" in n.lower() for n in names)


async def test_fulltext_matches_exact_brand(db_session) -> None:
    # The keyword arm catches an exact brand token the embedding might blur.
    ids = await fulltext_candidates(db_session, "Anker", candidate_k=3)
    names = await _names(db_session, ids)
    assert names and all("anker" in n.lower() for n in names)


async def test_fulltext_misses_cross_lingual(db_session) -> None:
    # German full-text returns nothing for an English phrase — this is *why* the
    # semantic arm exists; hybrid search needs both.
    ids = await fulltext_candidates(db_session, "pasta dinner", candidate_k=5)
    assert ids == []


# ── End-to-end behaviour through the full retriever ─────────────────────────


@asynccontextmanager
async def _provider(session):
    """A session_provider that hands the retriever the test's rolled-back session (not a new one)."""
    yield session


async def test_search_guenstige_windeln_returns_only_diapers(db_session, embedder) -> None:
    # The regression that drove the candidate filter: with the noise cut, "cheap diapers"
    # must return diapers — not a cheap-but-irrelevant coffee.
    from app.retrieval.hybrid import HybridRetriever
    from app.retrieval.vector_index import PgVectorIndex

    retriever = HybridRetriever(embedder, PgVectorIndex(), session_provider=lambda: _provider(db_session))
    hits = await retriever.search("günstige Windeln", top_k=5, sort=Sort.PRICE_LOW)
    assert hits
    assert all("windel" in h.name.lower() for h in hits)


async def test_search_pasta_dinner_spans_partners(db_session, embedder) -> None:
    # Cross-lingual + cross-partner: an English query finds German pasta from >1 partner.
    from app.retrieval.hybrid import HybridRetriever
    from app.retrieval.vector_index import PgVectorIndex

    retriever = HybridRetriever(embedder, PgVectorIndex(), session_provider=lambda: _provider(db_session))
    hits = await retriever.search("pasta dinner", top_k=8)
    assert hits
    assert len({h.partner for h in hits}) >= 2


async def test_search_partner_filter(db_session, embedder) -> None:
    from app.retrieval.hybrid import HybridRetriever
    from app.retrieval.vector_index import PgVectorIndex

    retriever = HybridRetriever(embedder, PgVectorIndex(), session_provider=lambda: _provider(db_session))
    hits = await retriever.search("shampoo", top_k=5, partner=PartnerSlug.DM)
    assert hits
    assert all(h.partner is PartnerSlug.DM for h in hits)
