# syntax=docker/dockerfile:1

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

# Bake the embedding model into a cache the runtime stage copies, so the image
# serves the local embedder offline with no runtime download.
ENV HF_HOME=/opt/hf-cache
RUN /app/.venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# ── Runtime: slim image with only what we need to serve ─────────────
FROM python:3.12-slim AS runtime

# Run as a non-root user.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Bring the resolved virtualenv and the cached embedding model from the builder.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder --chown=app:app /opt/hf-cache /opt/hf-cache
ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/opt/hf-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

COPY app/ ./app/
COPY data/ ./data/

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
