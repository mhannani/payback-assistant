"""LiteLLM gateway: the agent's vendor-neutral door to a chat model.

`get_chat_model` builds the configured `ChatLiteLLM` (provider chosen by the `llm_model`
setting; credentials read from the environment by LiteLLM).
"""

from app.llm.factory import get_chat_model

__all__ = ["get_chat_model"]
