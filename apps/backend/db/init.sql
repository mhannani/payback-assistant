-- Database bootstrap, run once when the Postgres container is first created.
-- Mirrors app/db/models.py. The ORM models are the source of truth for the app;
-- this script makes a fresh dev database usable without an extra migration step.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── partners ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS partners (
    id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(50)  NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL
);

-- ── brands ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS brands (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    name       VARCHAR(120) NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_brands_partner_name ON brands (partner_id, name);

-- ── products ─────────────────────────────────────────────────────────
-- Shared columns drive cross-partner search. `tags` (organic/vegan…) and the
-- normalized `weight_g`/`volume_ml` are extracted at ingestion so they are directly
-- filterable/rankable; rare partner-specific extras live in JSONB `attrs`.
-- `embedding` is the semantic vector; `search_tsv` is a generated full-text column
-- (German config) for the keyword half of hybrid search.
CREATE TABLE IF NOT EXISTS products (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id  UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    brand_id    UUID REFERENCES brands(id) ON DELETE SET NULL,
    name        VARCHAR(255) NOT NULL,
    description VARCHAR(1024),
    price_cents INTEGER NOT NULL,
    currency    VARCHAR(3) NOT NULL DEFAULT 'EUR',
    image_url   VARCHAR(1024),
    tags        TEXT[] NOT NULL DEFAULT '{}',
    weight_g    INTEGER,
    volume_ml   INTEGER,
    attrs       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Vector size is the embedding dimension, derived from the configured provider + model.
    -- data.init_db (the single schema path for every environment) substitutes ${EMBEDDING_DIM},
    -- so the column and the ORM never disagree on a hand-set number.
    embedding   VECTOR(${EMBEDDING_DIM}),
    -- Which embedder produced `embedding`; lets the embed step re-embed on a
    -- provider switch and lets retrieval reject a stale-model mismatch.
    embedding_model VARCHAR(120),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_tsv  TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('german', coalesce(name, '') || ' ' || coalesce(description, ''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS ix_products_partner    ON products (partner_id);
CREATE INDEX IF NOT EXISTS ix_products_brand      ON products (brand_id);
CREATE INDEX IF NOT EXISTS ix_products_tags_gin   ON products USING gin (tags);
CREATE INDEX IF NOT EXISTS ix_products_attrs_gin  ON products USING gin (attrs);
CREATE INDEX IF NOT EXISTS ix_products_search_tsv ON products USING gin (search_tsv);

-- Vector (ANN) index for semantic search. HNSW gives the best recall/latency
-- tradeoff and can be built on an empty table; cosine distance matches the
-- normalized text embeddings the assistant uses.
CREATE INDEX IF NOT EXISTS ix_products_embedding_hnsw
    ON products USING hnsw (embedding vector_cosine_ops);
