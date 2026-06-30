"""The intent agent as a LangGraph state machine.

The brief's agent in one diagram::

    START → classify ─┬─ search ─┬─ (hits)        → END
                      │          └─ (none) ─┬─ budget left → clarify
                      │                     └─ capped      → END (empty)
                      ├─ route                            → END
                      ├─ decline                          → END (out of scope)
                      └─ clarify → (interrupt; on resume) → classify

* **classify** — one LLM call (structured output) reads the WHOLE conversation (``messages``) and
  produces a :class:`Classification`; a pure policy (:func:`decide_action`) picks the next action.
* **search** / **route** — run the existing retriever (route = scoped to a named partner). If a
  search matches nothing, it redirects to clarify to ask the user to refine — unless the clarify
  budget is spent, in which case it ends with an empty result set rather than looping.
* **clarify** — ``interrupt()`` pauses to ask one question; the resumed answer is APPENDED to
  ``messages`` and re-enters classify (loop via routing, never a ``while`` inside the node —
  LangGraph's rule). The conversation accumulates, so the next classify sees every prior answer.

The clarify→resume loop is **bounded**. Each clarify increments ``clarify_count``; once it reaches
``_MAX_CLARIFICATIONS`` the classify node forces a search instead of asking again, so the agent
always terminates in products (or a route), honoring the brief's "products OR a clarifying question"
contract instead of clarifying forever. (The hand-rolled "fold the latest answer into a query string"
predecessor dropped earlier answers and never converged — see ``state.py`` for the memory model.)

Design choices worth calling out:

* **Conversation memory via ``add_messages``.** Turns accumulate in ``messages`` (the documented
  LangGraph short-term-memory primitive), so the classifier re-reads the full history each turn — no
  manual string concatenation, no lost context.
* **Routing with ``Command(goto=…, update=…)``.** Nodes that must *both* update state and choose
  the next node return a ``Command`` — the native LangGraph way to express "do this, then go there".
  The node that has the data (the hit count, the clarify budget) owns the routing decision.
* **The clarify question lives in state.** Whoever decides to clarify sets ``clarify_question``; the
  clarify node just asks it. One ask step, no duplicated question logic.
* **The search node owns its data access.** The retriever opens its own DB session, so nothing
  unserializable has to be threaded through the run config — graph state stays pure data.
"""

from typing import Any, Literal

from langchain_core.messages import HumanMessage
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
from app.retrieval.factory import get_cached_retriever
from app.retrieval.types import Sort
from app.shared.partner import partner_search_url

_CLARIFY = NextBestAction.CLARIFY.value
_SEARCH = NextBestAction.SEARCH.value
_ROUTE = NextBestAction.ROUTE_TO_PARTNER.value
_DECLINE = NextBestAction.DECLINE.value

# Convergence guard: the most clarifying questions one conversation may ask before the agent forces a
# search with everything it has gathered. The brief wants "products OR a clarifying question" — this
# bounds the clarify→resume loop so it always reaches a terminal answer (LangGraph's recommended shape
# for re-prompt loops is a bounded counter, not an open while-loop).
_MAX_CLARIFICATIONS = 3


async def classify_node(
    state: AgentState,
) -> Command[Literal["search", "route_to_partner", "clarify", "decline"]]:
    """Classify the WHOLE conversation → next action, then route there in one step.

    The ``Command[Literal[...]]`` return annotation is how LangGraph discovers this node's possible
    destinations (goto targets are runtime values it can't otherwise infer), so the compiled graph is
    correctly edged and drawable.

    The classifier reads ``state["messages"]`` — the opening query plus every clarification answer,
    accumulated by the ``add_messages`` reducer — so on a resume it re-classifies with the FULL added
    context (e.g. "etwas zu essen" + "Bio" + "fürs Abendessen"), not just the latest turn.

    Convergence: if the policy says CLARIFY but the conversation has already asked the maximum number
    of questions, force a search with everything gathered so far instead of asking again — the agent
    must terminate in products/route, never loop forever.
    """
    classification: Classification = await classifier_chain().ainvoke(
        {"messages": state["messages"]}
    )
    action = decide_action(classification)
    update: dict[str, Any] = {"classification": classification, "action": action}

    if action is NextBestAction.CLARIFY:
        if state.get("clarify_count", 0) >= _MAX_CLARIFICATIONS:
            # Budget spent — stop asking and search with the accumulated conversation.
            update["action"] = NextBestAction.SEARCH
            return Command(goto=_SEARCH, update=update)
        update["clarify_count"] = state.get("clarify_count", 0) + 1
        # The model proposes the question; fall back to a generic one in the user's language.
        update["clarify_question"] = (
            classification.clarification_question or _default_question(classification.language)
        )
        return Command(goto=_CLARIFY, update=update)

    return Command(goto=action.value, update=update)


async def search_node(state: AgentState) -> Command[Literal["clarify", "__end__"]]:
    """Run the retriever; on no results, redirect to clarify instead of a dead-end empty list."""
    return await _search_then_route(state["classification"], state.get("clarify_count", 0))


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


def decline_node(state: AgentState) -> Command[Literal["__end__"]]:
    """Out-of-scope guard: answer with a helpful hand-off, not products, and end.

    Two cases land here (see ``decide_action``): a ``customer_support`` query — orders/returns, which
    the assistant has no data for, so it hands the shopper to the partner's real service desk — and an
    ``off_topic`` query (not shopping at all), politely declined. A terminal step with NO retrieval and
    NO clarify (clarifying these just invites more of the same). Like the route node, this just ends;
    the helpful text is composed in the runner (``_decline_message``) next to the other per-language
    copy, and the response layer surfaces it as a first-class ``decline``. Scope stays structural —
    driven by the classifier's intent, not by phrase matching on the query.
    """
    return Command(goto=END)


def clarify_node(state: AgentState) -> Command[Literal["classify"]]:
    """Ask the pending question, pause, then resume into classify with the user's answer.

    Pure "ask" step: the question was decided upstream and put in ``clarify_question``. ``interrupt``
    suspends the run (state persisted under the thread_id) and returns the human's reply on resume —
    called exactly once per invocation, per LangGraph's interrupt rules. The reply is APPENDED to
    ``messages`` (via the ``add_messages`` reducer), so the next classify sees it alongside every
    earlier turn — the conversation accumulates rather than overwriting.
    """
    answer = interrupt(state["clarify_question"])
    return Command(goto="classify", update={"messages": [HumanMessage(content=answer)]})


async def _search_then_route(classification: Classification, clarify_count: int) -> Command:
    """Shared body for search/route: retrieve, then go to END or clarify based on results.

    When a search finds nothing, ask the user to refine — UNLESS the clarify budget is already spent,
    in which case end with an empty result set. That ends the conversation cleanly ("nothing found")
    instead of bouncing forced-search ↔ clarify forever once the cap is reached.
    """
    hits = await _run_search(classification)
    if hits:
        return Command(goto=END, update={"hits": hits})
    if clarify_count >= _MAX_CLARIFICATIONS:
        return Command(goto=END, update={"hits": []})
    # Nothing matched and we still have budget — ask the user to refine. This clarify counts toward
    # the cap, so the no-results path can't loop indefinitely either.
    return Command(
        goto=_CLARIFY,
        update={
            "hits": [],
            "action": NextBestAction.CLARIFY,
            "clarify_count": clarify_count + 1,
            "clarify_question": _no_results_question(classification.language),
        },
    )


async def _run_search(classification: Classification) -> list[Any]:
    """Call the same retriever the /search endpoint uses, with the agent's extracted parameters.

    The retriever owns its own data access, so the node passes only the search parameters.
    """
    return await get_cached_retriever().search(
        classification.search_query,
        partner=classification.partner,
        sort=classification.sort or Sort.RELEVANCE,
        require_tags=classification.require_tags or None,
    )


# German copy uses the formal "Sie" throughout — a retail brand addresses customers formally.
def _default_question(language: Language) -> str:
    """Generic clarifying question if the model didn't supply one."""
    if language is Language.DE:
        return "Können Sie genauer sagen, wonach Sie suchen?"
    return "Could you tell me a bit more about what you're looking for?"


def _no_results_question(language: Language) -> str:
    """Asked when a search returns nothing — invite the user to refine rather than dead-end."""
    if language is Language.DE:
        return "Dazu habe ich nichts gefunden. Können Sie es anders beschreiben?"
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
    builder.add_node(_DECLINE, decline_node)
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
