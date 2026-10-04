"""Alembic migration environment (async-aware).

Tied to the application's SQLAlchemy ``Base`` metadata (see
``tender_compliance_api.db.base``).  The schema source of truth is Alembic
migrations — this module does **not** call ``metadata.create_all()`` (per
AGENTS.md and docs/BYND-REUSE-AUDIT.md, the "app-startup schema
creation/migration" pattern is rejected).

The database URL is resolved in priority order so that both production and
tests work from one code path:

  1. ``sqlalchemy.url`` on the Alembic config (set by tests / CLI override).
  2. ``DATABASE_URL`` application setting (from the environment / ``.env``).

If neither is available, migration is refused with a clear error rather than
silently connecting to the wrong database.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make the installed package importable when running ``alembic`` from the
# project root.  The package uses a src-layout (apps/api/src); add it to
# sys.path so ``tender_compliance_api`` resolves for both CLI and tests.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tender_compliance_api.config import get_settings  # noqa: E402
from tender_compliance_api.db import models  # noqa: E402,F401
from tender_compliance_api.db.base import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Application model metadata.  Alembic uses this for autogenerate.
# All models register onto the Base in db/models.py (CP08+).
target_metadata = Base.metadata


def _resolve_url() -> str:
    """Resolve the database URL for migrations.

    Priority:
      1. ``sqlalchemy.url`` set on the Alembic config (tests / CLI override).
      2. ``DATABASE_URL`` application setting (environment / ``.env``).

    Raises:
        RuntimeError: If neither source provides a URL.
    """
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    url = get_settings().database_url
    if url:
        return url
    raise RuntimeError(
        "No database URL configured for Alembic migrations. "
        "Set sqlalchemy.url in alembic.ini, or DATABASE_URL in the environment."
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (URL only, no live connection)."""
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        # Ensure the alembic_version table has a wide enough version_num column.
        # Alembic's default is VARCHAR(32), but some revision identifiers (e.g.
        # "0025_missing_evidence_clarifications" = 37 chars) exceed that.
        # On PostgreSQL this causes ``value too long for type character
        # varying(32)``.  We create the table ourselves with VARCHAR(256) so
        # that Alembic's own _ensure_version_table() finds it already exists
        # and skips its default (narrower) DDL.  Created inside the
        # transaction so it is committed together with the migrations.
        from sqlalchemy import inspect as _inspect
        from sqlalchemy import text as _text

        inspector = _inspect(connection)
        if "alembic_version" not in inspector.get_table_names():
            connection.execute(
                _text(
                    "CREATE TABLE alembic_version ("
                    "version_num VARCHAR(256) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )

        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with an async engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _resolve_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
