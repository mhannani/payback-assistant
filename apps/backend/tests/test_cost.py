"""Cost accounting tests — hermetic (LiteLLM prices from a local table, no network)."""

from __future__ import annotations

from app.llm.cost import usage_from_callback


def test_no_usage_returns_none() -> None:
    assert usage_from_callback(None) is None
    assert usage_from_callback({}) is None


def test_prices_a_known_model() -> None:
    usage = usage_from_callback({"gpt-4o-mini": {"input_tokens": 500, "output_tokens": 50}})
    assert usage is not None
    assert usage.input_tokens == 500
    assert usage.output_tokens == 50
    assert usage.cost_usd is not None and usage.cost_usd > 0


def test_unpriceable_model_reports_unknown_cost_not_error() -> None:
    # A model LiteLLM can't price must not raise (the turn already succeeded) — cost is None,
    # while the token counts are still reported.
    usage = usage_from_callback({"some-unlisted-model-xyz": {"input_tokens": 10, "output_tokens": 5}})
    assert usage is not None
    assert usage.input_tokens == 10
    assert usage.cost_usd is None
