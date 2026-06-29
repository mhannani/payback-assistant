# syntax=docker/dockerfile:1
#
# Production image — lean. Embeddings are served by a managed provider (OpenAI / Vertex), so the
# image carries no model and no torch: a small image with fast cold starts, inference served
# off-host (the brief's "Vertex AI for model serving").

# ── Builder: resolve and install dependencies with uv ───────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ── Runtime: slim image with only what we need to serve ─────────────
FROM python:3.12-slim AS runtime

# Run as a non-root user.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY app/ ./app/
COPY data/ ./data/
COPY db/ ./db/

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
