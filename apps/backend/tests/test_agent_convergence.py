"""Hermetic convergence tests for the clarify→resume loop — no LLM, no DB, always run.

These prove the bug that motivated the fix can't recur: a clarify loop must TERMINATE in products
(or a route), never ask forever. They drive the real compiled graph with an in-process ``MemorySaver``
and two fakes — a classifier that is *permanently* vague (always ``needs_clarification=True``) and a
stubbed retriever — so the only thing under test is the graph's own convergence machinery: the
``add_messages`` accumulation and the ``_MAX_CLARIFICATIONS`` cap. No model or network, so they run in
every environment (unlike the key-gated end-to-end flow tests in test_assist_api.py).
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent import chains, graph
from app.agent.classification import Classification
from app.agent.graph import _MAX_CLARIFICATIONS, compile_agent
from app.agent.intents import Intent, Language
from app.retrieval.types import Sort


class _AlwaysVagueChain:
    """A classifier stand-in that NEVER stops asking — the worst case the cap must contain.

    It always reports ``needs_clarification=True`` with a concrete ``search_query``, modelling a model
    that keeps wanting "just one more detail". With the old string-folding code this looped forever;
    with the fix the cap forces a search after ``_MAX_CLARIFICATIONS`` rounds.
    """

    async def ainvoke(self, _inputs: dict) -> Classification:
        return Classification(
            intent=Intent.DISCOVERY,
            language=Language.EN,
            needs_clarification=True,
            clarification_question="Could you tell me a bit more?",
            partner=None,
            sort=Sort.RELEVANCE,
            require_tags=[],
            search_query="snacks",
            message=None,
        )


def _fake_hit() -> dict:
    """A sentinel 'hit' — the search node only checks the list's truthiness, not its element type.

    A plain dict (not ``object()``) so the MemorySaver checkpointer can serialize ``hits`` into state;
    these convergence tests assert on the graph's control flow, not on hit fields.
    """
    return {"id": "sentinel"}


@pytest.fixture
def _patch_classifier(monkeypatch):
    """Swap the classifier for the always-vague fake (and clear its lru_cache so the swap takes)."""
    chains.classifier_chain.cache_clear()
    monkeypatch.setattr(graph, "classifier_chain", lambda: _AlwaysVagueChain())
    yield
    chains.classifier_chain.cache_clear()


async def _drive_to_termination(agent, thread_id: str):
    """Open a conversation and keep answering until the graph stops interrupting (or we exceed the
    cap's worth of turns, which would mean it never converged). Returns the final state values."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await agent.ainvoke({"messages": [HumanMessage(content="I want something")]}, config)
    # One extra answer beyond the cap is the most a converging loop can need; more means a bug.
    for i in range(_MAX_CLARIFICATIONS + 2):
        if not result.get("__interrupt__"):
            break
        from langgraph.types import Command

        result = await agent.ainvoke(Command(resume=f"answer {i}"), config)
    return result


async def test_perpetually_vague_query_still_terminates_in_products(monkeypatch, _patch_classifier):
    """The bug, killed: an always-vague classifier must NOT clarify forever — the cap forces a search
    and the conversation ends with products (not a fourth, fifth, … question)."""
    monkeypatch.setattr(graph, "get_cached_retriever", lambda: _Retriever([_fake_hit()]))
    agent = compile_agent(MemorySaver())
    thread_id = uuid.uuid4().hex

    result = await _drive_to_termination(agent, thread_id)

    # Terminated: no pending interrupt, and it ended on a search that returned the stubbed hit.
    assert not result.get("__interrupt__"), "agent kept clarifying past the cap — loop didn't converge"
    assert result.get("hits"), "forced search should have produced products"

    # And it asked at most the cap's worth of questions before forcing the search.
    snapshot = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    assert snapshot.values["clarify_count"] == _MAX_CLARIFICATIONS


async def test_messages_accumulate_across_clarify_rounds(monkeypatch, _patch_classifier):
    """Every answer is retained: the conversation history compounds (the whole point of add_messages),
    so the classifier always sees the full context — not just the latest reply."""
    monkeypatch.setattr(graph, "get_cached_retriever", lambda: _Retriever([_fake_hit()]))
    agent = compile_agent(MemorySaver())
    thread_id = uuid.uuid4().hex

    await _drive_to_termination(agent, thread_id)

    snapshot = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    texts = [m.content for m in snapshot.values["messages"]]
    assert "I want something" in texts  # the opening turn survived
    # Each clarify answer we fed was appended, not overwritten.
    assert any(t.startswith("answer ") for t in texts)
    assert len([t for t in texts if t.startswith("answer ")]) == _MAX_CLARIFICATIONS


async def test_forced_search_with_no_hits_ends_empty_not_looping(monkeypatch, _patch_classifier):
    """When the cap forces a search that ALSO finds nothing, the agent ends with an empty product list
    ('nothing found') rather than bouncing forced-search ↔ clarify forever."""
    monkeypatch.setattr(graph, "get_cached_retriever", lambda: _Retriever([]))
    agent = compile_agent(MemorySaver())
    thread_id = uuid.uuid4().hex

    result = await _drive_to_termination(agent, thread_id)

    assert not result.get("__interrupt__"), "no-results past the cap must terminate, not re-clarify"
    assert result.get("hits") == [], "exhausted-budget empty search should end with no products"


class _Retriever:
    """Minimal retriever stub: returns a fixed hit list regardless of the query/params."""

    def __init__(self, hits: list):
        self._hits = hits

    async def search(self, *_args, **_kwargs) -> list:
        return self._hits
