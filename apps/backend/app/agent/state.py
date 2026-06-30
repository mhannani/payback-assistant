"""The agent graph's state, and the pure intent→action decision.

``AgentState`` is what flows through the LangGraph nodes and what the durable Postgres checkpointer
persists between an interrupt and its resume (keyed by ``thread_id``). It stays **serializable** —
plain data only, no live resources — which is what lets the checkpointer save/restore a paused
conversation. (The search node's retriever owns its own data access, so no DB session ever rides along.)

**Conversation memory.** The shopper's turns accumulate in ``messages`` via LangGraph's
``add_messages`` reducer — the documented short-term-memory primitive for multi-turn graphs. Each turn
(the opening query, then each clarification answer) is *appended*, not overwritten, so the classifier
always re-reads the FULL history and context compounds naturally across a clarify→resume loop. This
replaces a hand-rolled "fold the latest answer into a query string" approach (which dropped earlier
answers and made the agent clarify forever). ``clarify_count`` bounds that loop — see graph.py.

``decide_action`` is deliberately a small pure function, not part of the LLM call: the LLM *describes*
the conversation (a ``Classification``); this code *decides what to do about it*. Keeping the policy in
code (not in the prompt) makes the brief's "based on the intent, decide the Next Best Action" explicit,
auditable, and unit-testable without a model.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.agent.classification import Classification
from app.agent.intents import Intent, NextBestAction


class AgentState(TypedDict, total=False):
    """Data carried through the graph. ``total=False``: nodes fill fields as they run."""

    # The conversation so far. ``add_messages`` makes node returns APPEND to this list (not replace
    # it), so the opening query + every clarification answer accumulate across turns. The classifier
    # reads the whole list, so context compounds — the core of the multi-turn clarify→resume flow.
    messages: Annotated[list[AnyMessage], add_messages]
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
    # How many times this conversation has chosen to clarify. The convergence guard: once it hits the
    # cap (graph.py:_MAX_CLARIFICATIONS) the agent forces a search instead of asking again, so it
    # always terminates in products/route rather than looping forever.
    clarify_count: int


def decide_action(c: Classification) -> NextBestAction:
    """Map a classification to the next best action — the agent's core policy.

    Order matters. ``decline`` is checked FIRST: an out-of-scope request (write code, weather,
    chit-chat) must be refused outright — never clarified (which invites more off-topic) or searched
    (noise). Then clarify, because if the query is too vague (or is product-adjacent support) we must
    ask before doing anything — even if the model also guessed a partner. The model sometimes sets
    ``partner`` over-eagerly on a vague query; trusting it over the clarify signal would route a
    meaningless search and return an empty list. So:

    1. off-topic, or a support/orders question → **decline** (we hand off, not search);
    2. too vague                               → **clarify** (ask one question);
    3. names a specific shop                   → **route to that partner**;
    4. otherwise                               → **search** all partners.

    ``customer_support`` declines rather than clarifies: the assistant has no order/returns data, so
    asking "what are you looking for?" is wrong — the decline node instead hands the shopper to the
    partner's real service desk. ``off_topic`` declines too (out of scope entirely). Both produce a
    helpful message; the node tells them apart by intent.
    """
    if c.intent in (Intent.OFF_TOPIC, Intent.CUSTOMER_SUPPORT):
        return NextBestAction.DECLINE
    if c.needs_clarification:
        return NextBestAction.CLARIFY
    if c.partner is not None:
        return NextBestAction.ROUTE_TO_PARTNER
    return NextBestAction.SEARCH
