# syntax=docker/dockerfile:1
#
# Production image — lean and cloud-first. It installs the cloud embedder extra (Vertex / OpenAI)
# and NOT the local one, so torch and the bundled model are absent: a small image with fast cold
# starts, with inference served off-host (the brief's "Vertex AI for model serving"). The offline,
# torch-based local embedder is the dev image's job (Dockerfile.dev), used for the runnable demo.

# ── Builder: resolve and install dependencies with uv ───────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached unless the lockfile changes). `--extra cloud` adds the Vertex
# and OpenAI SDKs; `--no-dev` and no `--extra local` keep torch/sentence-transformers out.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra cloud

# ── Runtime: slim image with only what we need to serve ─────────────
FROM python:3.12-slim AS runtime

# Run as a non-root user.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY app/ ./app/
COPY data/ ./data/

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
