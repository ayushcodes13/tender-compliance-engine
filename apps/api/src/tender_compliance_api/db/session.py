"""Async SQLAlchemy 2.x engine and session boundary.

This module owns the engine and session factory for the application.
Routes and services must never create their own engines — they must
inject sessions via the ``get_session`` FastAPI dependency.

Decision: an **async** engine is used because FastAPI is async-first and
the product will perform I/O-heavy work (parsing, OCR, retrieval). The
async choice is explicit, not an implicit framework default.

The schema source of truth is Alembic (see CP07); this module does **not**
call ``metadata.create_all()`` (see BYND-REUSE-AUDIT.md: "App-startup
schema creation/migration" pattern is rejected).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tender_compliance_api.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(
    database_url: str | None = None,
    **engine_kwargs: Any,
) -> AsyncEngine:
    """Initialize the async engine and session factory.

    Uses ``database_url`` when provided, otherwise falls back to the
    ``DATABASE_URL`` application setting.

    Idempotent: calling with an already-initialized engine returns the
    existing engine without re-creating it.

    Args:
        database_url: Connection URL. If ``None``, uses
            ``settings.database_url``.
        **engine_kwargs: Additional keyword arguments forwarded to
            ``sqlalchemy.ext.asyncio.create_async_engine`` (e.g.
            ``connect_args``, ``poolclass`` for SQLite testing).

    Returns:
        The configured :class:`AsyncEngine`.

    Raises:
        ValueError: If no database URL can be resolved.
    """
    global _engine, _session_factory

    url: str | None = database_url if database_url is not None else get_settings().database_url

    if not url:
        raise ValueError(
            "DATABASE_URL is required but was not provided. "
            "Set the DATABASE_URL environment variable."
        )

    if _engine is not None:
        return _engine

    logger.info("Initializing database engine")
    _engine = create_async_engine(url, **engine_kwargs)
    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return _engine


async def close_engine() -> None:
    """Dispose of the async engine and clear the session factory."""
    global _engine, _session_factory

    if _engine is not None:
        logger.info("Disposing database engine")
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session.

    Inject this into any route or service that needs a database session::

        from fastapi import Depends
        from tender_compliance_api.db.session import get_session

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...

    Raises:
        RuntimeError: If the engine has not been initialized via
            :func:`init_engine`.
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database engine is not initialized. Call init_engine() before using get_session()."
        )

    async with _session_factory() as session:
        yield session
