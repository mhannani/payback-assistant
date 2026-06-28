"""The intent agent as a LangGraph state machine.

The brief's agent in one diagram::

    START → classify ─┬─ search ─┬─ (hits)  → END
                      │          └─ (none)  → clarify
                      ├─ route  ─┬─ (hits)  → END
                      │          └─ (none)  → clarify
                      └─ clarify → (interrupt; on resume) → classify

* **classify** — one LLM call (structured output) turns the raw query into a
  :class:`Classification`; a pure policy (:func:`decide_action`) picks the next action.
* **search** / **route** — run the existing retriever (route = scoped to a named partner). If
  nothing matches, they redirect to clarify and ask the user to refine, rather than returning an
  empty list.
* **clarify** — ``interrupt()`` pauses to ask one question; the resumed answer re-enters
  classify (loop via routing, never a ``while`` inside the node — LangGraph's rule).

Design choices worth calling out:

* **Routing with ``Command(goto=…, update=…)``.** Nodes that must *both* update state and choose
  the next node return a ``Command`` — the native LangGraph way to express "do this, then go
  there" — instead of a separate edge function re-deriving the decision from state. The node
  that has the data (e.g. the hit count) owns the routing decision.
* **The clarify question lives in state.** Whoever decides to clarify (classify when vague,
  search/route when empty) sets ``clarify_question``; the clarify node just asks it. One ask
  step, no duplicated question logic.
* **Session travels in ``config``, not state.** The checkpointer serializes state to pause a
  conversation; a live DB session can't be serialized, so it is injected per request via
  ``config["configurable"]["session"]``.
"""

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

# NOTE: this module intentionally does NOT use `from __future__ import annotations`.
# LangGraph discovers each node's possible destinations by introspecting its return annotation
# (`Command[Literal["search", ...]]`) at runtime via get_type_hints. With postponed evaluation
# the annotation would be a plain string and that introspection would silently fail, so the
# graph would run but render with no dynamic edges. Keeping annotations as real objects here is
# what lets LangGraph build (and draw) the correct edge set.

from app.agent.chains import classifier_chain
from app.agent.classification import Classification
from app.agent.intents import Language, NextBestAction
from app.agent.state import AgentState, decide_action
from app.retrieval.factory import get_retriever
from app.retrieval.types import Sort
from app.shared.partner import partner_search_url

_CLARIFY = NextBestAction.CLARIFY.value
_SEARCH = NextBestAction.SEARCH.value
_ROUTE = NextBestAction.ROUTE_TO_PARTNER.value


async def classify_node(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["search", "route_to_partner", "clarify"]]:
    """LLM call → Classification → next action, then route there in one step.

    The ``Command[Literal[...]]`` return annotation is how LangGraph discovers this node's
    possible destinations (goto targets are runtime values it can't otherwise infer), so the
    compiled graph is correctly edged and drawable.

    On a resume after clarification the user's answer is folded into the query so the model
    re-classifies with the added context (e.g. "etwas zu essen" + answer "Nudeln").
    """
    query = state["query"]
    if state.get("answer"):
        query = f"{query}. {state['answer']}"

    classification: Classification = await classifier_chain().ainvoke({"query": query})
    action = decide_action(classification)

    update: dict[str, Any] = {
        "classification": classification,
        "action": action,
        "answer": None,  # consume any resumed answer so a later turn won't reuse it
    }
    if action is NextBestAction.CLARIFY:
        # The model proposes the question; fall back to a generic one in the user's language.
        update["clarify_question"] = (
            classification.clarification_question or _default_question(classification.language)
        )
    return Command(goto=action.value, update=update)


async def search_node(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["clarify", "__end__"]]:
    """Run the retriever; on no results, redirect to clarify instead of a dead-end empty list."""
    return await _search_then_route(state["classification"], config)


def route_node(state: AgentState) -> Command[Literal["__end__"]]:
    """Navigational hand-off: the shopper wants a specific partner's *own* search.

    This is the brief's "route to a specific partner search" — distinct from ``search``. We do
    NOT answer from our catalog; we build a deep-link into the named partner's native product
    search for the cleaned query and end. The client renders it as a link/button so the user
    lands directly in that shop's search.
    """
    c = state["classification"]
    deeplink = partner_search_url(c.partner, c.search_query)
    return Command(goto=END, update={"deeplink": deeplink})


def clarify_node(state: AgentState) -> Command[Literal["classify"]]:
    """Ask the pending question, pause, then resume into classify with the user's answer.

    Pure "ask" step: the question was decided upstream and put in ``clarify_question``.
    ``interrupt`` suspends the run (state persisted under the thread_id) and returns the human's
    reply on resume — called exactly once per invocation, per LangGraph's interrupt rules.
    """
    answer = interrupt(state["clarify_question"])
    return Command(goto="classify", update={"answer": answer})


async def _search_then_route(classification: Classification, config: RunnableConfig) -> Command:
    """Shared body for search/route: retrieve, then go to END or clarify based on results."""
    hits = await _run_search(classification, config)
    if hits:
        return Command(goto=END, update={"hits": hits})
    # Nothing matched — ask the user to refine rather than returning an empty product list.
    return Command(
        goto=_CLARIFY,
        update={
            "hits": [],
            "action": NextBestAction.CLARIFY,
            "clarify_question": _no_results_question(classification.language),
        },
    )


async def _run_search(classification: Classification, config: RunnableConfig) -> list[Any]:
    """Call the same retriever the /search endpoint uses, with the agent's extracted parameters.

    The request-scoped session comes from config (not state — see module docstring).
    """
    session = config["configurable"]["session"]
    return await get_retriever().search(
        session,
        classification.search_query,
        partner=classification.partner,
        sort=classification.sort or Sort.RELEVANCE,
        require_tags=classification.require_tags or None,
    )


def _default_question(language: Language) -> str:
    """Generic clarifying question if the model didn't supply one."""
    if language is Language.DE:
        return "Kannst du genauer sagen, wonach du suchst?"
    return "Could you tell me a bit more about what you're looking for?"


def _no_results_question(language: Language) -> str:
    """Asked when a search returns nothing — invite the user to refine rather than dead-end."""
    if language is Language.DE:
        return "Dazu habe ich nichts gefunden. Kannst du es anders beschreiben?"
    return "I couldn't find anything for that. Could you describe it differently?"


def build_graph() -> StateGraph:
    """Assemble the agent's nodes and entry edge (uncompiled).

    Nodes route via ``Command(goto=…)``, so the only static edge is START → classify; every
    other transition is dynamic (classify → search/route/clarify; search → END or clarify;
    clarify → classify). Kept separate from compilation so the graph can be compiled with
    whatever checkpointer the caller supplies.
    """
    builder = StateGraph(AgentState)
    builder.add_node("classify", classify_node)
    builder.add_node(_SEARCH, search_node)
    builder.add_node(_ROUTE, route_node)
    builder.add_node(_CLARIFY, clarify_node)
    builder.add_edge(START, "classify")
    return builder


def compile_agent(checkpointer):
    """Compile the agent graph with a checkpointer.

    The compiled graph is stateless and thread-safe — compile it ONCE for the app's lifetime and
    reuse it across all conversations; per-conversation state lives in the checkpointer, keyed by
    ``thread_id``. The app lifespan compiles with the durable Postgres checkpointer and stores
    the result on ``app.state.agent``; tests compile with an in-process ``MemorySaver``.
    """
    return build_graph().compile(checkpointer=checkpointer)
