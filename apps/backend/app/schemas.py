"""API response models.

These are the JSON shapes the API returns — kept separate from the internal retrieval
types (``SearchHit``) so the wire contract can evolve independently of the internals.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.agent.intents import Intent, Language, NextBestAction
from app.retrieval.ranking._common import unit_price_from_hit
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
    # Comparative price normalized to a 100-unit base — the metric "cheapest" really means (a 1 L
    # bottle can beat a 200 ml one even at a higher shelf price). null when the product has no
    # parseable size. ``unit_basis`` names the base ("per_100g" / "per_100ml") so the figure is
    # never read as a shelf price. Surfaced on every product so a comparison view can show value,
    # not just the sticker number.
    unit_price_cents: int | None
    unit_basis: str | None

    @classmethod
    def from_hit(cls, hit: SearchHit) -> ProductOut:
        unit = unit_price_from_hit(hit)
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
            unit_basis=unit[0] if unit else None,
            unit_price_cents=unit[1] if unit else None,
        )


# ── Intent agent response ───────────────────────────────────────────
# The assistant answers a query with ONE of five shapes — recommended products, a value comparison, a
# clarifying question, a hand-off to a partner's own search, or a helpful decline (out of scope:
# support or off-topic). Modelling that as a discriminated union (on ``type``) makes the contract
# explicit: the client switches on ``type`` and the OpenAPI schema documents every branch, instead of
# one model with most fields null. ``intent``/``action`` are surfaced so a caller (or a reviewer) can
# see *why* the agent answered the way it did.


class UsageOut(BaseModel):
    """What the turn cost: token counts (LangChain) priced in USD (LiteLLM). See app.llm.cost.

    Returned on every branch as a **demo convenience** so a client can sum cost per turn (the
    brief's "cost per 1000 requests"). In production this belongs in telemetry or a debug header,
    not the public response body — it's here to make the cost transparently measurable.
    """

    model: str
    input_tokens: int
    output_tokens: int
    # null when LiteLLM has no pricing for the model — tokens are known, the dollar figure isn't.
    cost_usd: float | None = None


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
    # An optional helpful one-liner the model wrote alongside the classification (e.g. a short framing
    # of the results). null for a plain search; the products themselves are the answer.
    message: str | None = None


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


class DeclineResponse(_AssistBase):
    """The query is out of the assistant's scope — it answers with a helpful hand-off, not products.

    Two cases share this shape: a ``customer_support`` query (orders/returns — handed to the named
    partner's real service desk) and an ``off_topic`` query (not about shopping at all — politely
    declined). ``message`` is the helpful reply; ``partner`` is set when the hand-off names one so the
    client can surface that partner's contact. Distinct from ``clarify`` on purpose: there is no
    follow-up question and no ``thread_id`` — the conversation ends here.
    """

    type: Literal["decline"] = "decline"
    message: str
    partner: PartnerSlug | None = None
    partner_name: str | None = None


class CompareResponse(_AssistBase):
    """The shopper wanted to weigh options — the agent answers with a value comparison.

    Distinct from ``products`` on purpose: it adds comparison *meaning* the plain list doesn't. The
    ``items`` are ordered by price-per-unit (cheapest value first, not cheapest sticker), each carrying
    its ``unit_price_cents``; ``cheapest_pick`` highlights the best-value item (``items[0]``, or null
    when nothing matched). ``message`` is the model's short framing line. The wire stays presentation-
    neutral — a client may render the items as a table, but the contract is the data, not the layout.
    """

    type: Literal["compare"] = "compare"
    items: list[ProductOut]
    cheapest_pick: ProductOut | None
    message: str | None = None


# Discriminated union: FastAPI/Pydantic pick the branch by the ``type`` field.
AssistResponse = Annotated[
    ProductsResponse | ClarifyResponse | RouteResponse | DeclineResponse | CompareResponse,
    Field(discriminator="type"),
]
