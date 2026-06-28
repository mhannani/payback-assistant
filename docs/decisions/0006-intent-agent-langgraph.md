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
change (`llm_model`, e.g. `openai/gpt-4o-mini` → `vertex_ai/gemini-2.0-flash`) with credentials
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

## The structured contract

`/assist` (and `/assist/resume`) return a discriminated union on `type`:
`products` | `clarify` | `route`. The client switches on `type`; the OpenAPI schema documents
every branch. Resuming an unknown/finished thread returns a clean `404`, not a crash.

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
