"""Regression tests for UUID primary-key round-tripping on SQLite (CP06/CP08).

SQLite applies NUMERIC column affinity to columns whose declared type name it
does not recognise (such as ``UUID``).  SQLAlchemy's stock
``UUID(as_uuid=True)`` binds the UUID's ``hex`` form — 32 hex digits *without*
dashes.  A UUID whose hex happens to be all-decimal (notably the deterministic
single-workspace bootstrap IDs
``00000000-0000-0000-0000-000000000001`` / ``...002``) is then silently stored
as a Python ``int`` and crashes the result processor on the next read
(``AttributeError: 'int' object has no attribute 'replace'``).

The app uses :class:`~tender_compliance_api.db.types.TcuUUID` for every UUID
column (``db.models`` aliases it as ``SaUUID``); that type binds the canonical
dash-separated string, which NUMERIC affinity preserves as TEXT, and coerces
results back to :class:`uuid.UUID`.

These tests persist the *exact* problematic IDs through the migration-built
test schema (the same schema the application uses) and read them back on a fresh
session/connection — the precise path that used to crash.
"""

from __future__ import annotations

import asyncio
import uuid

from tender_compliance_api.db.models import Organization, User

ZERO_USER = uuid.UUID("00000000-0000-0000-0000-000000000001")
ZERO_ORG = uuid.UUID("00000000-0000-0000-0000-000000000002")


def test_single_workspace_zero_uuids_round_trip(session_cm) -> None:
    """The deterministic single-workspace IDs must survive a SQLite write+read.

    Mirrors ``_single_workspace_context``: an org + owner are bootstrapped on
    the first request, then looked up with ``session.get`` on every subsequent
    request.  With the stock UUID type the second request raised 500.
    """

    async def _run() -> None:
        async with session_cm() as session:
            session.add(
                Organization(id=ZERO_ORG, name="Tender Compliance Workspace")
            )
            session.add(
                User(
                    id=ZERO_USER,
                    auth_provider="single_workspace",
                    auth_provider_user_id=str(ZERO_USER),
                    full_name="Pilot Workspace",
                )
            )
            await session.commit()

        # A second, independent session forces a real database round-trip
        # (separate identity map) — the path that previously raised
        # AttributeError on SQLite.
        async with session_cm() as session:
            org = await session.get(Organization, ZERO_ORG)
            user = await session.get(User, ZERO_USER)

            assert org is not None
            assert isinstance(org.id, uuid.UUID)
            assert org.id == ZERO_ORG

            assert user is not None
            assert isinstance(user.id, uuid.UUID)
            assert user.id == ZERO_USER

    asyncio.run(_run())


def test_random_uuids_still_round_trip(session_cm) -> None:
    """Non-zero UUIDs (the common case) must continue to round-trip."""

    async def _run() -> None:
        uid = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=uid, name="Random Org"))
            await session.commit()

        async with session_cm() as session:
            org = await session.get(Organization, uid)
            assert org is not None
            assert isinstance(org.id, uuid.UUID)
            assert org.id == uid

    asyncio.run(_run())
