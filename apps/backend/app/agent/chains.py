"""The LLM chains the agent's nodes invoke.

Each LLM task is a small chain — ``prompt | model.with_structured_output(Schema)`` — defined
here and invoked from a thin graph node, so the LLM task (prompt + schema + model) stays
separate from the graph wiring (nodes + edges) and each is read, changed, and tested on its own.

The model is reached through ``get_chat_model()`` (a ``ChatLiteLLM`` gateway), so the provider
is a config choice. ``with_structured_output(Classification)`` constrains the model to return
the exact schema, validated — no string parsing.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from app.agent.classification import Classification
from app.llm import get_chat_model

# The classifier's instruction. Per-field guidance lives in the Classification field
# descriptions (which the schema sends to the model); this sets the role and the one rule that
# most affects quality — prefer searching, clarify only when genuinely necessary.
_CLASSIFY_SYSTEM = """\
You are the intent classifier for a multilingual shopping assistant that searches across the \
dm, EDEKA, and Amazon product catalogs. Classify the user's message into the provided schema.

Guidelines:
- Detect the language (German or English).
- Choose 'search' for a concrete product need, 'discovery' for vague browsing, 'comparison' \
for weighing options, 'customer_support' for non-product requests (returns, help).
- Strongly prefer searching. If the message contains ANY concrete product noun or category \
(e.g. "pasta dinner", "Windeln", "coffee", "shampoo"), set needs_clarification=false and \
search — even if it's brief. Set needs_clarification=true ONLY when there is no searchable \
product term at all (e.g. "I want something", "etwas Schönes", "ideas?").
- Map price intent (günstige, cheap, billig) to sort=price_low.
- Set partner ONLY when the user names a specific shop (dm, edeka, amazon).
- Put the cleaned core product terms in search_query, in the original language.\
"""

_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _CLASSIFY_SYSTEM), ("human", "{query}")]
)


@lru_cache
def classifier_chain():
    """Build the classify chain once: prompt → model → validated ``Classification``.

    Lazily constructed (and cached) rather than a module-level constant because building the
    model touches settings/credentials; deferring it keeps importing this module side-effect
    free, which matters for tests that don't exercise the LLM.
    """
    model = get_chat_model()
    return _CLASSIFY_PROMPT | model.with_structured_output(Classification)
