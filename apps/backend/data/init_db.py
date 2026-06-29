"""Apply the database schema (``db/init.sql``) to whatever database is configured.

In local dev the Postgres container runs ``init.sql`` automatically on first boot. A managed
database (RDS, Cloud SQL, or any plain Postgres) has no such hook, so this script is the
reproducible way to create the schema there: it executes the *same* ``init.sql`` — one source of
truth for dev and cloud — through the app's own connection settings.

``init.sql`` is idempotent (``CREATE … IF NOT EXISTS`` throughout), so this is safe to run before
every seed. It is the first step of the deploy-time seed job (init → seed → embed).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.db.session import engine

# db/ sits next to app/ and data/ in the image and the repo.
INIT_SQL = Path(__file__).resolve().parent.parent / "db" / "init.sql"


async def init_db() -> None:
    """Run db/init.sql against the configured database."""
    sql = INIT_SQL.read_text()
    # The asyncpg driver runs a multi-statement script in one call via the raw connection's
    # ``execute`` (SQLAlchemy's text() binds a single statement, which this script is not).
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(sql)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
    print(f"Applied schema from {INIT_SQL.name}.")
