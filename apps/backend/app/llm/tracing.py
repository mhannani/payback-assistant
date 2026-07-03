"""Langfuse tracing for the agent's LLM calls — wired at the LiteLLM callback layer.

Every model call the agent makes goes through LiteLLM (``ChatLiteLLM`` wraps it), so one
process-level callback traces them all — model, tokens, latency, prompt and structured response —
with no per-call-site instrumentation.

We run Langfuse **v3** self-hosted (``observability/docker-compose.langfuse.yml``), so the documented
integration is the **OpenTelemetry** path, ``litellm.callbacks = ["langfuse_otel"]`` — NOT the
v2-only ``success_callback = ["langfuse"]``. LiteLLM's exporter reads the keys + host from the
environment and posts spans to ``{LANGFUSE_OTEL_HOST}/api/public/otel``.
(Ref: docs.litellm.ai/docs/observability/langfuse_otel_integration)

Telemetry must never break a turn: everything is gated on ``LANGFUSE_ENABLED`` and wrapped in
try/except — a Langfuse outage degrades to "no traces", never to a failed request.
"""

from __future__ import annotations

import logging
import os

from app.config import Settings

logger = logging.getLogger(__name__)

_initialized = False


def init_langfuse(settings: Settings) -> None:
    """Register LiteLLM's ``langfuse_otel`` callback once, if tracing is configured.

    Called from ``get_chat_model`` (itself cached), so the callback is registered before the
    first model call and exactly once per process. A no-op when disabled or misconfigured.
    """
    global _initialized
    if _initialized or not settings.langfuse_enabled:
        return
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning("LANGFUSE_ENABLED is set but keys are missing — tracing disabled")
        return
    try:
        import litellm

        # LiteLLM's exporter reads these exact env names; setting them here means the settings
        # object stays the single source and nothing else needs the raw environment.
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
        if settings.langfuse_otel_host:
            os.environ["LANGFUSE_OTEL_HOST"] = settings.langfuse_otel_host

        # Append, don't clobber — other callbacks may be registered.
        existing = litellm.callbacks if isinstance(litellm.callbacks, list) else []
        if "langfuse_otel" not in existing:
            litellm.callbacks = [*existing, "langfuse_otel"]

        _initialized = True
        logger.info("Langfuse tracing enabled (otel host: %s)", settings.langfuse_otel_host)
    except Exception:  # never let telemetry wiring break startup or a turn
        logger.warning("Langfuse init failed — tracing disabled", exc_info=True)
