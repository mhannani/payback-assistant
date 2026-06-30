"""Retrieval result types.

``SearchHit`` is one ranked product returned by a retriever — a self-contained view
(no further DB lookup needed) carrying the fields a caller renders plus the final
ranking ``score``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.shared.partner import PartnerSlug


class Sort(StrEnum):
    """How to order results among the relevant set.

    The agent picks this from the query ("günstige" → PRICE_LOW); the retriever just
    applies it. RELEVANCE is the default — price only ever re-orders relevant hits.
    More orderings (e.g. PRICE_HIGH, RATING) can be added without touching callers.
    """

    RELEVANCE = "relevance"
    PRICE_LOW = "price_low"


class RetrievalCapability(StrEnum):
    """A retrieval arm a backend supports. Surfaced in a retriever's ``capabilities`` so the
    hybrid-vs-vector-only difference between backends is an explicit, inspectable part of the
    contract (e.g. on /config) rather than a hidden behavioural surprise.

    VECTOR = semantic similarity (every backend). FULLTEXT = keyword/lexical matching (Postgres
    German full-text; BigQuery has no equivalent, so its retriever is vector-only).
    """

    VECTOR = "vector"
    FULLTEXT = "fulltext"


@dataclass(frozen=True, slots=True)
class Candidate:
    """The minimal per-candidate facts ranking needs — independent of SQL/ORM.

    A retriever builds these from its backend rows (Postgres today, BigQuery later) and
    hands them to the ranking layer; keeping them backend-free is what makes ranking
    engine-portable. This is an internal type — the public result is ``SearchHit``.
    """

    product_id: uuid.UUID
    partner: PartnerSlug
    fused_score: float
    price_cents: int
    weight_g: int | None
    volume_ml: int | None


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One ranked product returned by a retriever — the public retrieval result."""

    product_id: uuid.UUID
    partner: PartnerSlug
    name: str
    brand: str | None
    description: str | None
    price_cents: int
    currency: str
    image_url: str | None
    tags: list[str]
    weight_g: int | None
    volume_ml: int | None
    score: float  # final fused + normalized + boosted score; higher is better
    attrs: dict[str, Any] = field(default_factory=dict)
