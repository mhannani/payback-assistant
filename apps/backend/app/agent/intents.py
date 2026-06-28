"""The agent's vocabulary: what a query can mean and what to do about it.

Three small enums, deliberately separate, mirroring the codebase's existing ``StrEnum`` style
(``PartnerSlug``, ``Sort``):

* ``Intent`` — *what the user is trying to do*. The four categories the brief names.
* ``Language`` — *what language they wrote in*. German is required; English is supported.
* ``NextBestAction`` — *what the agent should do next*. The three actions the brief lists.

Intent and action are kept apart on purpose: the same intent can lead to different actions
(a SEARCH intent normally runs a search, but if the query is too vague it routes to CLARIFY),
so collapsing them into one enum would hard-code a mapping that should be explicit and
testable. The mapping lives in the graph's routing logic, not in the type.
"""

from __future__ import annotations

from enum import StrEnum


class Intent(StrEnum):
    """What the user is trying to do — the brief's four intent categories."""

    SEARCH = "search"  # a concrete product need: "günstige Windeln", "Anker headphones"
    DISCOVERY = "discovery"  # vague/browsing: "something for breakfast" — often needs clarifying
    COMPARISON = "comparison"  # weighing options: "compare the cheapest pasta"
    CUSTOMER_SUPPORT = "customer_support"  # not a product query: returns/help — out of catalog scope


class Language(StrEnum):
    """The query language. German is required by the brief; English is supported."""

    DE = "de"
    EN = "en"


class NextBestAction(StrEnum):
    """What the agent does next — the brief's three agent actions.

    SEARCH: the query is specific → run a catalog search and return products.
    CLARIFY: the query is too vague to act on → ask one clarifying question.
    ROUTE_TO_PARTNER: the query is navigational ("show me dm's …") → search scoped to a partner.
    """

    SEARCH = "search"
    CLARIFY = "clarify"
    ROUTE_TO_PARTNER = "route_to_partner"
