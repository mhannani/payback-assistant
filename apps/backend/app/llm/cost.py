"""Per-turn LLM usage and cost — tokens counted by LangChain, priced by LiteLLM.

This is the seam between two libraries that don't connect on their own. Verified against the docs:

* **LangChain counts tokens, never dollars.** ``get_usage_metadata_callback`` returns
  ``{model: {input_tokens, output_tokens, total_tokens, ...}}`` — token counts only. (Cost in
  dollars is a LangSmith feature with its own price table, not part of this callback.)
* **LiteLLM prices tokens.** ``cost_per_token(model, prompt_tokens, completion_tokens)`` knows each
  model's current price — so we never hand-maintain a $/token table.

We use the callback (rather than reading the one classify call's message) because it's the
framework-native aggregator and stays correct if a turn ever makes more than one call. Today a
turn makes exactly ONE LLM call (the classify node; search/route/clarify call no model), and a
resume is its own turn with its own single call.

WHY cost is surfaced on the API at all: this is a take-home demo, and returning the cost makes
"cost per 1000 requests" transparently measurable by a client (see ``perf/``). In production this
would move to telemetry or a debug header rather than the public response body — it is here as a
documented demo convenience, not a recommended public contract.
"""

from __future__ import annotations

from app.schemas import UsageOut


def usage_from_callback(usage_metadata: dict[str, dict] | None) -> UsageOut | None:
    """Build a :class:`~app.schemas.UsageOut` from ``get_usage_metadata_callback().usage_metadata``.

    That callback yields ``{model_name: {input_tokens, output_tokens, total_tokens, ...}}`` summed
    over the run. We collapse it to one :class:`UsageOut`, pricing each model's tokens via LiteLLM.
    Returns ``None`` when no usage was recorded, so callers can omit the field rather than report a
    fabricated zero.
    """
    if not usage_metadata:
        return None

    # The callback keys usage by model. One model is used here, but iterating the dict consumes
    # the callback's contract as-is (and a resume's repeated calls are already merged per model).
    # If LiteLLM can't price any model, cost is reported as unknown (None) — not a fabricated zero,
    # and never a raised error: pricing is a reporting convenience and must not fail a turn whose
    # model call already succeeded.
    total_input = 0
    total_output = 0
    total_cost: float | None = 0.0
    for model, counts in usage_metadata.items():
        input_tokens = int(counts.get("input_tokens", 0))
        output_tokens = int(counts.get("output_tokens", 0))
        total_input += input_tokens
        total_output += output_tokens
        priced = _cost_usd(model, input_tokens, output_tokens)
        total_cost = None if priced is None or total_cost is None else total_cost + priced

    return UsageOut(
        model="+".join(usage_metadata),
        input_tokens=total_input,
        output_tokens=total_output,
        cost_usd=None if total_cost is None else round(total_cost, 8),
    )


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """LiteLLM's dollar cost for the given model + token counts, or ``None`` if it can't price it."""
    # Imported here so the module loads without litellm installed (and only the agent path,
    # which already requires it, ever calls this).
    from litellm import cost_per_token

    try:
        prompt_cost, completion_cost = cost_per_token(
            model=model, prompt_tokens=input_tokens, completion_tokens=output_tokens
        )
        return prompt_cost + completion_cost
    except Exception:
        # LiteLLM raises for a model it has no pricing for. The turn succeeded; report cost unknown.
        return None
