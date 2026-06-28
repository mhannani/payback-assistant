"""Run the agent graph for one HTTP turn and shape the result.

The endpoints stay thin: they hand a query (or a resume answer) here, and get back the
discriminated-union response. This module owns the two things that are fiddly about driving a
LangGraph with human-in-the-loop over HTTP:

1. **Threading the request session in via config** — the graph's search node needs the DB
   session, which can't live in (serializable) graph state, so it travels in
   ``config["configurable"]["session"]`` alongside the ``thread_id`` the checkpointer keys on.
2. **Detecting the interrupt** — when the clarify node calls ``interrupt()``, the graph returns
   with an ``__interrupt__`` payload instead of finishing. That is the signal to return a
   clarifying question (and the ``thread_id`` to resume with) rather than products.
"""

from __future__ import annotations

import uuid

from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import (
    AssistResponse,
    ClarifyResponse,
    ProductOut,
    ProductsResponse,
    RouteResponse,
)
from app.shared.partner import PARTNER_DISPLAY_NAMES


class UnknownThreadError(Exception):
    """Raised when a resume targets a thread that isn't paused awaiting an answer.

    Either the thread_id was never created or its conversation already finished. The endpoint
    maps this to a 404 — without the guard, resuming an unknown thread would start the graph
    with no input and crash on the missing query.
    """


async def start_assist(agent, query: str, session: AsyncSession) -> AssistResponse:
    """Begin a new conversation: classify the query and act on it.

    ``agent`` is the compiled graph (passed in, not a global) so the caller controls its
    lifecycle — the app supplies the one compiled with the durable checkpointer.
    """
    thread_id = uuid.uuid4().hex
    result = await agent.ainvoke(
        {"query": query},
        config={"configurable": {"thread_id": thread_id, "session": session}},
    )
    return _to_response(result, thread_id)


async def resume_assist(agent, thread_id: str, answer: str, session: AsyncSession) -> AssistResponse:
    """Continue a paused conversation with the user's answer to a clarifying question."""
    config = {"configurable": {"thread_id": thread_id, "session": session}}

    # A resumable thread is one paused mid-run (its `next` points at the node to continue). An
    # unknown or already-finished thread has no pending step — reject it cleanly rather than
    # resuming into an empty graph state.
    snapshot = await agent.aget_state(config)
    if not snapshot.next:
        raise UnknownThreadError(thread_id)

    result = await agent.ainvoke(Command(resume=answer), config=config)
    return _to_response(result, thread_id)


def _to_response(result: dict, thread_id: str) -> AssistResponse:
    """Map the graph's end state to a products or clarify response.

    ``result["__interrupt__"]`` is present iff the run paused at the clarify node; its payload is
    the question we surfaced via ``interrupt(question)``.
    """
    interrupts = result.get("__interrupt__")
    classification = result["classification"]
    common = {
        "intent": classification.intent,
        "action": result["action"],
        "language": classification.language,
    }

    if interrupts:
        return ClarifyResponse(
            **common, question=interrupts[0].value, thread_id=thread_id
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
    from app.agent.intents import Language

    name = PARTNER_DISPLAY_NAMES[classification.partner]
    if classification.language is Language.DE:
        return f"Ich leite dich zur Suche bei {name} weiter."
    return f"I'll take you to {name}'s search."
