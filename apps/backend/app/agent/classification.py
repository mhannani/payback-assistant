"""The structured result the LLM must produce for a query.

``Classification`` is the schema handed to ``with_structured_output`` — the LLM is constrained
to return exactly these fields, validated into this object. It is the contract between "natural
language in" and "mechanical retrieval parameters out".

Read the ``Field(description=...)`` text as *prompt*: those descriptions are what the model
sees for each field, so they are written to instruct, not just to document. Keep them concrete
and aligned with the retriever's real capabilities (partner / sort / tags), because the agent
maps these straight onto ``/search``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent.intents import Intent, Language
from app.retrieval.types import Sort
from app.shared.partner import PartnerSlug


class Classification(BaseModel):
    """What the LLM extracts from a raw query, mapped to the retriever's knobs."""

    intent: Intent = Field(
        description=(
            "The user's goal. 'search' = a concrete product need (e.g. 'günstige Windeln'). "
            "'discovery' = vague browsing (e.g. 'something for breakfast'). 'comparison' = "
            "weighing options. 'customer_support' = not a product query (returns, help)."
        )
    )
    language: Language = Field(
        description="The language the query is written in: 'de' for German, 'en' for English."
    )
    needs_clarification: bool = Field(
        description=(
            "True only when the query is too vague to search usefully and a single clarifying "
            "question would materially improve the result. Prefer searching when in doubt."
        )
    )
    # NOTE: fields are required-but-nullable (no Python defaults) on purpose — OpenAI's strict
    # structured-output mode demands every property appear in the schema's `required` list, so an
    # "optional" field is modelled as ``X | None`` the model must always emit (null when N/A),
    # not a field with a default the model may omit.
    clarification_question: str | None = Field(
        description=(
            "If needs_clarification is true, one short question to ask the user, in their "
            "language (e.g. 'Suchst du eher Süßes oder Herzhaftes?'). Otherwise null."
        ),
    )
    partner: PartnerSlug | None = Field(
        description=(
            "Set ONLY when the user names a specific shop to search within (dm, edeka, amazon) "
            "— a navigational/routing request. Otherwise null (search all partners)."
        ),
    )
    sort: Sort = Field(
        description=(
            "'price_low' when the user signals they want the cheapest / best value "
            "(e.g. 'günstige', 'cheap', 'billig'). Otherwise 'relevance'."
        ),
    )
    require_tags: list[str] = Field(
        description=(
            "Dietary requirements the products must satisfy, from this set only: organic, "
            "vegan, vegetarian, no-gluten, no-lactose, halal, kosher, fair-trade. Empty if none."
        ),
    )
    search_query: str = Field(
        description=(
            "The cleaned query to send to product search — the core product terms, with "
            "filler and intent words removed (e.g. 'günstige Windeln kaufen' → 'Windeln'). "
            "Keep it in the original language."
        )
    )
