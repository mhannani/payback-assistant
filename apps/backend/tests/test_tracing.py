"""Langfuse tracing wiring tests — hermetic (no Langfuse instance, no model call).

Tracing is optional telemetry: these prove the gate — disabled or misconfigured means NO callback
is registered and nothing breaks — and that enabling it registers LiteLLM's ``langfuse_otel``
callback exactly once.
"""

from __future__ import annotations

import litellm
import pytest

from app.config import Settings
from app.llm import tracing
from app.llm.tracing import init_langfuse


@pytest.fixture(autouse=True)
def _reset_tracing_state(monkeypatch):
    """Isolate each test: fresh module gate, and litellm callbacks restored afterwards."""
    monkeypatch.setattr(tracing, "_initialized", False)
    before = list(litellm.callbacks) if isinstance(litellm.callbacks, list) else litellm.callbacks
    yield
    litellm.callbacks = before


def _callback_names() -> list[str]:
    return [c for c in (litellm.callbacks or []) if isinstance(c, str)]


def test_disabled_registers_nothing() -> None:
    init_langfuse(Settings(langfuse_enabled=False))
    assert "langfuse_otel" not in _callback_names()


def test_enabled_without_keys_registers_nothing() -> None:
    # Misconfiguration degrades to "no traces" with a warning — never a crash.
    init_langfuse(Settings(langfuse_enabled=True))
    assert "langfuse_otel" not in _callback_names()
    assert not tracing._initialized


def test_enabled_with_keys_registers_once(monkeypatch) -> None:
    settings = Settings(
        langfuse_enabled=True,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
        langfuse_otel_host="http://langfuse:3000",
    )
    init_langfuse(settings)
    assert _callback_names().count("langfuse_otel") == 1
    # Idempotent: a second call (fresh gate, same process) must not double-register.
    monkeypatch.setattr(tracing, "_initialized", False)
    init_langfuse(settings)
    assert _callback_names().count("langfuse_otel") == 1
