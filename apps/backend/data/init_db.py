"""Apply the database schema (``db/init.sql``) to whatever database is configured.

This is the **single** schema-creation path for every environment — dev, RDS, Cloud SQL, or any
plain Postgres. Dev does not rely on the Postgres image's init hook and the cloud has none, so the
schema is always created the same way: run the same ``init.sql`` through the app's own connection.
It is the first step of seeding everywhere (init → seed → embed).

``init.sql`` carries a ``${EMBEDDING_DIM}`` placeholder for the vector column size; we substitute
the configured dimension here so the column matches the active embedder — one declared dimension,
no magic number duplicated between the schema and the ORM. ``init.sql`` is idempotent
(``CREATE … IF NOT EXISTS`` throughout), so this is safe to run before every seed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from string import Template

from app.config import get_settings
from app.db.session import engine

# db/ sits next to app/ and data/ in the image and the repo.
INIT_SQL = Path(__file__).resolve().parent.parent / "db" / "init.sql"


async def init_db() -> None:
    """Run db/init.sql (with the embedding dimension filled in) against the configured database."""
    sql = Template(INIT_SQL.read_text()).substitute(EMBEDDING_DIM=get_settings().embedding_dim)
    # The asyncpg driver runs a multi-statement script in one call via the raw connection's
    # ``execute`` (SQLAlchemy's text() binds a single statement, which this script is not).
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(sql)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
    print(f"Applied schema from {INIT_SQL.name}.")
