"""Build the chat model the agent talks to.

One place turns the ``llm_model`` setting into a model object, so the agent depends only on a
LangChain chat-model interface — never a vendor SDK. The model is a ``ChatLiteLLM``: LiteLLM is a
unified gateway over many providers, so switching OpenAI ↔ Vertex ↔ Anthropic is a one-line
config change (``llm_model``), with credentials read from the environment by LiteLLM itself.

``ChatLiteLLM`` exposes that gateway as a normal LangChain chat model that supports
``with_structured_output``, so the agent's classify step gets typed, validated output regardless
of the underlying provider.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.config import Settings, get_settings


@lru_cache
def get_chat_model(settings: Settings | None = None) -> Any:
    """Return the configured ``ChatLiteLLM`` (built once, cached).

    ``litellm.drop_params = True`` is set here because model families accept different params —
    some reject a non-default temperature, some rename ``max_tokens`` — and with drop_params on,
    LiteLLM strips/translates incompatible kwargs per model, so this one call site stays
    model-agnostic. Imports are local so the module loads even before the LLM deps are installed.
    """
    s = settings or get_settings()

    import litellm
    from langchain_litellm import ChatLiteLLM

    litellm.drop_params = True
    # Register Langfuse tracing (if configured) before the first model is built, so every call
    # through this gateway is traced from turn one. A no-op when LANGFUSE_ENABLED is unset.
    from app.llm.tracing import init_langfuse

    init_langfuse(s)
    return ChatLiteLLM(model=s.llm_model, temperature=s.llm_temperature)
