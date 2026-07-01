# 0006 — Intent agent: a LangGraph state machine over the retrieval primitive

**Status:** Accepted · **Date:** 2026-06-28

## Context

The assistant must take a raw natural-language query and decide what to do with it: search the
catalogs, ask a clarifying question, or send the shopper to a specific partner's own search. The
retrieval engine (ADRs 0001–0005) is deliberately a *mechanical* primitive — it does not
interpret intent. Something in front of it has to classify the query and choose the action, and
return a structured response that is *either* products *or* a question.

## Decision

Build the agent as a **LangGraph state machine**:

```
START → classify ─┬─ search ─┬─ (hits) → END
                  │          └─ (none) → clarify
                  ├─ route  → END
                  └─ clarify → (interrupt; on resume) → classify
```

- **classify** — one LLM call with `with_structured_output(Classification)` extracts intent,
  language, and the mechanical parameters (partner, sort, tags, cleaned query). A pure function
  `decide_action` maps that to the next action — policy lives in code, not the prompt.
- **search / route / clarify** — the three actions. `search` runs the existing retriever;
  `route` builds a deep-link into the partner's own search (a hand-off, not our results);
  `clarify` asks one question.
- Routing uses `Command(goto=…, update=…)` from the nodes (the node with the data owns the
  decision), so there are no separate edge functions to keep in sync.

### Why LangGraph

The control flow *is* a state machine with a human-in-the-loop pause: classify → branch →
maybe ask → resume. LangGraph gives the branch (`Command`/conditional edges), the pause/resume
(`interrupt` + a checkpointer + `thread_id`), and an inspectable, drawable graph — instead of
bespoke session and loop plumbing.

### The LLM gateway (provider-agnostic)

The model is reached through **`ChatLiteLLM`** (`app/llm/`), so the provider is a one-line config
change (`llm_model`, e.g. `openai/gpt-4o-mini` → `vertex_ai/gemini-2.5-flash`) with credentials
read from the environment. `with_structured_output` constrains the model to the `Classification`
schema — typed, validated output, no string parsing. (OpenAI strict mode requires every field in
`required`, so "optional" fields are modelled as required-but-nullable.)

### Durable conversation state

The clarify flow pauses with `interrupt()` and resumes on a later HTTP call, so graph state must
persist between turns. We use **`AsyncPostgresSaver`** (the database the service already runs),
not the in-process `MemorySaver` — paused conversations then survive a restart and span multiple
instances. Its lifecycle is owned by an `async with` context manager held open by the FastAPI
lifespan; the compiled agent is built once and stored on `app.state`. (`MemorySaver` is fine for
tests and scripts.)

### Multi-turn refinement: conversation memory + a bounded loop

The brief asks for a one-shot decision (products **or** a clarifying question). We extend it to a
**bounded multi-turn refinement**: a clarifying answer resumes the graph and re-classifies. The turns
accumulate in `state["messages"]` via LangGraph's **`add_messages`** reducer — the documented
short-term-memory primitive — so the classifier always re-reads the full conversation and context
compounds (an opener "etwas zu essen" + "italienisch" + "Pasta" eventually names a concrete product
and searches). This deliberately avoids hand-folding the latest answer into a query string, which
drops earlier turns and never converges. A `clarify_count` cap (`graph.py:_MAX_CLARIFICATIONS`) bounds
the loop: after N questions the agent forces a search with everything gathered, so it always
terminates in products/route rather than clarifying forever — LangGraph's recommended shape for a
re-prompt loop (a bounded counter, not an open `while`).

### Value comparison + scope guardrails (beyond the brief)

The brief asks the agent to *detect* four intents; we make two of them *do* something distinct rather
than fall through to a plain search:

- **`comparison` → a value comparison.** The compare node forces `Sort.PRICE_LOW`, so results are
  ranked by **price-per-unit** (cheapest *value* first, not cheapest sticker — a 1 L bottle can beat a
  200 ml one at a higher shelf price). Each product carries a normalized `unit_price_cents` + a
  `unit_basis` (`per_100g` / `per_100ml`), and `cheapest_pick` highlights the best value. This reuses
  the ranker's existing `price_per_unit` formula (`retrieval/ranking/_common.py`) — the comparison the
  API shows and the order the ranker produces agree on "value", one source of truth. A comparison that
  names a shop compares *within* it (`decide_action` checks comparison before route).
- **`off_topic` / `customer_support` → a helpful decline.** Out-of-scope requests (write code, weather)
  and orders/returns are refused rather than searched/clarified. Support hands off to the partner's
  **real service desk** (`shared/partner.py:PARTNER_CONTACTS`). Scope is enforced *structurally* — by
  the classifier's intent, not brittle phrase matching (the documented anti-jailbreak stance).

Two cheap, brief-neutral guards round it out: German copy uses the formal **Sie** throughout, and an
input-length cap rejects oversized `/assist`/`/resume` bodies (`422`) before any model call.

## The structured contract

`/assist` (and `/assist/resume`) return a discriminated union on `type`:
`products` | `compare` | `clarify` | `route` | `decline`. The client switches on `type`; the OpenAPI
schema documents every branch. Resuming an unknown/finished thread returns a clean `404`, not a crash.
The compiled state machine (rendered in [`../images/agent_graph.png`](../images/agent_graph.png)):
`classify` fans out to `search`/`compare`/`route`/`decline`/`clarify`; `search` ends with products or
redirects to `clarify` on no results; `clarify` interrupts and resumes back into `classify`.

## Consequences

- Intent interpretation is isolated from retrieval, so each is tested independently: the agent's
  pure logic (intent→action policy, deep-link building) is hermetic and always runs; the
  LLM-driven flows are integration-tested behind an API-key gate.
- Swapping LLM provider or the checkpointer backend is a config/lifespan change, not a rewrite.
- A token-streaming chat UI is a possible future enhancement (the graph supports `astream`); the
  current request/response contract is deliberate given the small structured payload and the
  pause/resume semantics.

## References

- LangGraph graph API, `Command`, and human-in-the-loop `interrupt`:
  <https://docs.langchain.com/oss/python/langgraph/graph-api>
- LangGraph Postgres checkpointer (`AsyncPostgresSaver`):
  <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangChain structured output (`with_structured_output`):
  <https://docs.langchain.com/oss/python/langchain/structured-output>
