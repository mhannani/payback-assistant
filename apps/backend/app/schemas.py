"""API response models.

These are the JSON shapes the API returns — kept separate from the internal retrieval
types (``SearchHit``) so the wire contract can evolve independently of the internals.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.agent.intents import Intent, Language, NextBestAction
from app.retrieval.types import SearchHit
from app.shared.partner import PARTNER_DISPLAY_NAMES, PartnerSlug


class ProductOut(BaseModel):
    """One recommended product in a search response.

    Result *position* is the ranking signal: the list is already ordered by the chosen
    strategy (relevance, then cross-partner fairness, then the requested sort). The raw
    fused relevance score is deliberately not exposed — fairness re-ordering makes it
    non-monotonic with position, so returning it would only invite "why is this out of
    order?" Order is the contract; the internal score stays internal (``SearchHit.score``).
    """

    id: uuid.UUID
    partner: PartnerSlug
    partner_name: str
    name: str
    brand: str | None
    description: str | None
    price_cents: int
    currency: str
    image_url: str | None
    tags: list[str]

    @classmethod
    def from_hit(cls, hit: SearchHit) -> ProductOut:
        return cls(
            id=hit.product_id,
            partner=hit.partner,
            partner_name=PARTNER_DISPLAY_NAMES[hit.partner],
            name=hit.name,
            brand=hit.brand,
            description=hit.description,
            price_cents=hit.price_cents,
            currency=hit.currency,
            image_url=hit.image_url,
            tags=hit.tags,
        )


# ── Intent agent response ───────────────────────────────────────────
# The assistant answers a query with ONE of three shapes — recommended products, a clarifying
# question, or a hand-off to a partner's own search. Modelling that as a discriminated union (on
# ``type``) makes the contract explicit: the client switches on ``type`` and the OpenAPI schema
# documents every branch, instead of one model with most fields null. ``intent``/``action`` are
# surfaced so a caller (or a reviewer) can see *why* the agent answered the way it did.


class UsageOut(BaseModel):
    """What the turn cost: token counts (LangChain) priced in USD (LiteLLM). See app.llm.cost.

    Returned on every branch as a **demo convenience** so a client can sum cost per turn (the
    brief's "cost per 1000 requests"). In production this belongs in telemetry or a debug header,
    not the public response body — it's here to make the cost transparently measurable.
    """

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class _AssistBase(BaseModel):
    """Fields every assist branch shares: why the agent answered (intent/action/language) and
    what the turn cost (usage). The discriminated branches add their own payload below."""

    intent: Intent
    action: NextBestAction
    language: Language
    usage: UsageOut | None = None


class ProductsResponse(_AssistBase):
    """The agent understood a concrete request and searched the catalogs."""

    type: Literal["products"] = "products"
    items: list[ProductOut]


class ClarifyResponse(_AssistBase):
    """The query was too vague (or out of catalog scope); the agent asks one question.

    ``thread_id`` ties the answer back to this paused conversation: the client replies via
    ``POST /assist/resume`` with this id, and the graph continues from where it paused.
    """

    type: Literal["clarify"] = "clarify"
    question: str
    thread_id: str


class RouteResponse(_AssistBase):
    """The query was navigational — the shopper wants a specific partner's own search.

    Rather than answer from our catalog, the agent hands off: it returns a deep-link into that
    partner's native product search for the query, which the client renders as a link/button.
    This is the brief's "route to a specific partner search" action.
    """

    type: Literal["route"] = "route"
    partner: PartnerSlug
    partner_name: str
    search_query: str
    deeplink: str
    message: str


# Discriminated union: FastAPI/Pydantic pick the branch by the ``type`` field.
AssistResponse = Annotated[
    ProductsResponse | ClarifyResponse | RouteResponse, Field(discriminator="type")
]
