"""Tests for the database session boundary (CP06).

These tests verify that the SQLAlchemy async engine/session layer:
- rejects invalid configuration clearly;
- opens and closes sessions through a reusable boundary;
- surfaces a clear error when the engine is not initialized.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

# Reuse the session-scoped test database URL from conftest so the engine
# restored in the uninitialized test matches the one the fixture initialised.
from conftest import TEST_DATABASE_URL
from sqlalchemy import text

from tender_compliance_api.db.session import (
    close_engine,
    get_session,
    init_engine,
)


def test_init_engine_rejects_empty_url():
    """init_engine must fail clearly when given an empty database URL."""
    with pytest.raises(ValueError, match="DATABASE_URL"):
        init_engine("")


def test_session_open_close():
    """A session can be opened and closed through the session boundary."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            assert session is not None
            assert session.is_active
            # Execute a query to autobegin a transaction so we can
            # verify it is cleaned up when the context exits.
            await session.execute(text("SELECT 1"))
            assert session.in_transaction()
        # After the boundary exits, the active transaction must be closed.
        # Note: SQLAlchemy 2.0+ Session.is_active does not track open/closed
        # state (only partial-rollback state), so in_transaction() is the
        # correct postcondition for cleanup verification.
        assert not session.in_transaction()

    asyncio.run(_run())


def test_session_can_execute_query():
    """A session can execute a simple query (SELECT 1) through the boundary."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1

    asyncio.run(_run())


def test_get_session_raises_when_uninitialized():
    """get_session raises RuntimeError when the engine is not initialized."""
    asyncio.run(close_engine())
    try:
        with pytest.raises(RuntimeError, match="not initialized"):
            asyncio.run(_raise_if_session_unavailable())
    finally:
        # Restore the engine for any subsequent tests.
        init_engine(TEST_DATABASE_URL)


async def _raise_if_session_unavailable():
    """Helper: attempt to open a session when the engine is closed."""
    async with asynccontextmanager(get_session)():
        # Should never reach here.
        raise AssertionError("Session should not be available after close_engine()")
