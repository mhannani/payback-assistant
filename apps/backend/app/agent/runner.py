"""Run the agent graph for one HTTP turn and shape the result.

The endpoints stay thin: they hand a query (or a resume answer) here, and get back the
discriminated-union response. The fiddly part of driving a LangGraph with human-in-the-loop over
HTTP is **detecting the interrupt**: when the clarify node calls ``interrupt()``, the graph returns
with an ``__interrupt__`` payload instead of finishing — the signal to return a clarifying question
(and the ``thread_id`` to resume with) rather than products. (The search node owns its own data
access, so no DB session is threaded through the run config.)
"""

from __future__ import annotations

import uuid

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.agent.intents import Intent, Language, NextBestAction
from app.llm.cost import usage_from_callback
from app.schemas import (
    AssistResponse,
    ClarifyResponse,
    DeclineResponse,
    ProductOut,
    ProductsResponse,
    RouteResponse,
    UsageOut,
)
from app.shared.partner import PARTNER_DISPLAY_NAMES, partner_contact


class UnknownThreadError(Exception):
    """Raised when a resume targets a thread that isn't paused awaiting an answer.

    Either the thread_id was never created or its conversation already finished. The endpoint
    maps this to a 404 — without the guard, resuming an unknown thread would start the graph
    with no input and crash on the missing query.
    """


async def start_assist(agent, query: str) -> AssistResponse:
    """Begin a new conversation: classify the query and act on it.

    ``agent`` is the compiled graph (passed in, not a global) so the caller controls its
    lifecycle — the app supplies the one compiled with the durable checkpointer.
    """
    thread_id = uuid.uuid4().hex
    # get_usage_metadata_callback sums token usage across every model call in the run (LangChain's
    # native aggregator) — so we never thread tokens through graph state. We price it after.
    with get_usage_metadata_callback() as cb:
        result = await agent.ainvoke(
            # Seed the conversation's first turn. The graph accumulates later answers into this list
            # (add_messages reducer), so the classifier always re-reads the full history.
            {"messages": [HumanMessage(content=query)]},
            config={"configurable": {"thread_id": thread_id}},
        )
    return _to_response(result, thread_id, usage_from_callback(cb.usage_metadata))


async def resume_assist(agent, thread_id: str, answer: str) -> AssistResponse:
    """Continue a paused conversation with the user's answer to a clarifying question."""
    config = {"configurable": {"thread_id": thread_id}}

    # A resumable thread is one paused mid-run (its `next` points at the node to continue). An
    # unknown or already-finished thread has no pending step — reject it cleanly rather than
    # resuming into an empty graph state.
    snapshot = await agent.aget_state(config)
    if not snapshot.next:
        raise UnknownThreadError(thread_id)

    with get_usage_metadata_callback() as cb:
        result = await agent.ainvoke(Command(resume=answer), config=config)
    return _to_response(result, thread_id, usage_from_callback(cb.usage_metadata))


def _to_response(result: dict, thread_id: str, usage: UsageOut | None) -> AssistResponse:
    """Map the graph's end state to one of the four assist responses.

    ``result["__interrupt__"]`` is present iff the run paused at the clarify node; its payload is
    the question we surfaced via ``interrupt(question)``. ``usage`` is this turn's LLM token/cost
    (see app.llm.cost), attached to every branch so a client can sum cost per turn.
    """
    interrupts = result.get("__interrupt__")
    classification = result["classification"]
    action = result["action"]
    common = {
        "intent": classification.intent,
        "action": action,
        "language": classification.language,
        "usage": usage,
    }

    if interrupts:
        return ClarifyResponse(
            **common, question=interrupts[0].value, thread_id=thread_id
        )

    if action is NextBestAction.DECLINE:
        # Out of scope (support / off-topic): a helpful hand-off, not products. The message names the
        # partner's real service desk when the support query named one.
        partner = classification.partner
        return DeclineResponse(
            **common,
            message=_decline_message(classification),
            partner=partner,
            partner_name=PARTNER_DISPLAY_NAMES[partner] if partner else None,
        )

    if result.get("deeplink"):
        return RouteResponse(
            **common,
            partner=classification.partner,
            partner_name=PARTNER_DISPLAY_NAMES[classification.partner],
            search_query=classification.search_query,
            deeplink=result["deeplink"],
            message=_route_message(classification),
        )

    return ProductsResponse(
        **common, items=[ProductOut.from_hit(h) for h in result.get("hits", [])]
    )


def _route_message(classification) -> str:
    """A short hand-off line in the user's language for a navigational query."""
    name = PARTNER_DISPLAY_NAMES[classification.partner]
    if classification.language is Language.DE:
        return f"Ich leite Sie zur Suche bei {name} weiter."
    return f"I'll take you to {name}'s search."


def _decline_message(classification) -> str:
    """The helpful reply for an out-of-scope query, in the user's language (formal Sie).

    For ``customer_support`` we hand the shopper to the *partner's* real service desk (the assistant
    has no order/returns data of its own); when the query named a partner we quote that partner's
    actual contact. For ``off_topic`` — and a support query that named no partner — a short, honest
    "this is a product-search assistant" line.
    """
    de = classification.language is Language.DE
    if classification.intent is Intent.CUSTOMER_SUPPORT and classification.partner is not None:
        name = PARTNER_DISPLAY_NAMES[classification.partner]
        c = partner_contact(classification.partner)
        hours = f" ({c.hours})" if c.hours else ""
        channels = ", ".join(filter(None, [c.email, c.extra]))
        if de:
            tail = f" Weitere Wege: {channels}." if channels else ""
            return (
                f"Bei Fragen zu Bestellungen oder Retouren hilft Ihnen der {name}-Kundenservice "
                f"unter {c.phone}{hours} weiter.{tail}"
            )
        tail = f" Other ways: {channels}." if channels else ""
        return (
            f"For orders or returns, {name}'s customer service can help you at "
            f"{c.phone}{hours}.{tail}"
        )
    if classification.intent is Intent.CUSTOMER_SUPPORT:
        if de:
            return (
                "Bei Fragen zu Bestellungen oder Retouren wenden Sie sich bitte an den "
                "Kundenservice des jeweiligen Händlers. Bei der Produktsuche helfe ich gern."
            )
        return (
            "For orders or returns, please contact the retailer's customer service. "
            "I'm happy to help with product searches."
        )
    # off_topic
    if de:
        return "Ich kann Ihnen nur bei der Produktsuche helfen."
    return "I can only help you with product searches."
