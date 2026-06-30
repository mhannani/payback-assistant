"""DSN construction tests — both the POSTGRES_* TCP path (local/AWS) and the explicit DATABASE_URL
override (Cloud SQL unix socket). Pure: no database connection."""

from __future__ import annotations

from app.config import Settings

SOCKET = "postgresql+asyncpg://payback:pw@/payback?host=/cloudsql/proj:eu:inst"


def test_tcp_dsn_built_from_parts_when_no_override() -> None:
    # The AWS/local guarantee: with no DATABASE_URL, both DSNs build host:port from POSTGRES_*.
    s = Settings(postgres_host="db", postgres_port=5432, postgres_db="payback", postgres_user="u")
    assert s.database_url == "postgresql+asyncpg://u:payback@db:5432/payback"
    assert s.checkpoint_db_url == "postgresql://u:payback@db:5432/payback"


def test_override_socket_dsn_preserved_for_both_drivers() -> None:
    # Cloud SQL: the injected socket DSN wins, and the ?host=/cloudsql/... query survives for both
    # the asyncpg (app) and libpq (checkpointer) forms — only the driver scheme differs.
    s = Settings(_env_file=None, DATABASE_URL=SOCKET)
    assert s.database_url == SOCKET  # asyncpg form unchanged
    assert s.checkpoint_db_url == (
        "postgresql://payback:pw@/payback?host=/cloudsql/proj:eu:inst"  # +asyncpg stripped
    )


def test_override_accepts_plain_scheme_and_adds_asyncpg() -> None:
    # A plain postgresql:// override is normalized to +asyncpg for the app, plain for the checkpointer.
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@/db?host=/cloudsql/x")
    assert s.database_url == "postgresql+asyncpg://u:p@/db?host=/cloudsql/x"
    assert s.checkpoint_db_url == "postgresql://u:p@/db?host=/cloudsql/x"
