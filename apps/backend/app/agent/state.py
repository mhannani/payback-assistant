"""The agent graph's state, and the pure intent→action decision.

``AgentState`` is what flows through the LangGraph nodes and what the checkpointer persists
between an interrupt and its resume. It stays **serializable** — plain data only, no live
resources — which is what lets the checkpointer save/restore a paused conversation. (The search
node's retriever owns its own data access, so no DB session ever has to ride along.)

``decide_action`` is deliberately a small pure function, not part of the LLM call: the LLM
*describes* the query (a ``Classification``); this code *decides what to do about it*. Keeping
the policy in code (not in the prompt) makes the brief's "based on the intent, decide the Next
Best Action" explicit, auditable, and unit-testable without a model.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.agent.classification import Classification
from app.agent.intents import Intent, NextBestAction


class AgentState(TypedDict, total=False):
    """Data carried through the graph. ``total=False``: nodes fill fields as they run."""

    query: str  # the raw user query (input)
    classification: Classification  # filled by the classify node
    action: NextBestAction  # filled by the classify node (decide_action)
    hits: list[Any]  # SearchHit list, filled by the search node
    # The partner deep-link the route node hands off to (navigational queries). A plain URL
    # string so it stays serializable for the checkpointer.
    deeplink: str | None
    # The question the clarify node will ask. It is set by whoever *decides* to clarify — the
    # classify node (query too vague) or the search node (no results, please refine) — so the
    # clarify node stays a pure "ask" step and the question logic isn't duplicated.
    clarify_question: str | None
    answer: str | None  # the user's reply to a clarification (on resume)


def decide_action(c: Classification) -> NextBestAction:
    """Map a classification to the next best action — the agent's core policy.

    Order matters, and clarify is checked FIRST on purpose: if the query is too vague (or is a
    support request) we must ask before doing anything — even if the model also guessed a
    partner. The model sometimes sets ``partner`` over-eagerly on a vague query; trusting it
    over the clarify signal would route a meaningless search and return an empty list. So:

    1. too vague / not a product query  → **clarify** (ask one question);
    2. names a specific shop            → **route to that partner**;
    3. otherwise                        → **search** all partners.
    """
    if c.needs_clarification or c.intent is Intent.CUSTOMER_SUPPORT:
        return NextBestAction.CLARIFY
    if c.partner is not None:
        return NextBestAction.ROUTE_TO_PARTNER
    return NextBestAction.SEARCH
