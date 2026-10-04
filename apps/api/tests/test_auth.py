"""Tests for the organization/identity/audit foundation (CP08).

Covers:
- Dev-mode auth context resolution (valid, missing, invalid, cross-tenant).
- Deny-by-default: the FastAPI dependency raises 401 without a valid actor.
- Cross-tenant denial: a membership-verified org is never overridden by a
  browser-supplied org ID.
- Audit events are organization-scoped and flushed.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService, write_audit_event
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.auth.deps import get_auth_context
from tender_compliance_api.auth.service import resolve_auth_context
from tender_compliance_api.config import Settings
from tender_compliance_api.db.models import AuditLog, Membership, Organization, User
from tender_compliance_api.db.session import get_session

DEV_USER_HEADER = "x-dev-user-id"
DEV_ORG_HEADER = "x-dev-organization-id"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(headers: dict[str, str] | None = None) -> Request:
    """Build a minimal Starlette Request with the given headers."""
    scope: dict = {"type": "http", "headers": []}
    if headers:
        scope["headers"] = [
            (k.lower().encode(), v.encode()) for k, v in headers.items()
        ]
    return Request(scope)


async def _create_dev_identity(
    session: AsyncSession,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    role: str = "owner",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a dev-mode user, org, and membership.  Returns (user_id, org_id)."""
    user_id = user_id or uuid.uuid4()
    org_id = org_id or uuid.uuid4()
    session.add(Organization(id=org_id, name=f"Org {org_id}"))
    session.add(
        User(id=user_id, auth_provider="dev", auth_provider_user_id=str(user_id))
    )
    session.add(
        Membership(organization_id=org_id, user_id=user_id, role=role)
    )
    await session.flush()
    return user_id, org_id


# ---------------------------------------------------------------------------
# Auth context resolution — development mode
# ---------------------------------------------------------------------------


def test_resolve_dev_context_valid():
    """Valid dev headers + existing membership yield a verified AuthContext."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            user_id, org_id = await _create_dev_identity(session)
            headers = {
                DEV_USER_HEADER: str(user_id),
                DEV_ORG_HEADER: str(org_id),
            }
            auth = await resolve_auth_context(session, headers)
            assert auth is not None
            assert auth.actor_id == user_id
            assert auth.organization_id == org_id
            assert "owner" in auth.roles

    asyncio.run(_run())


def test_resolve_denied_no_headers():
    """No dev headers → None (deny-by-default)."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            auth = await resolve_auth_context(session, {})
            assert auth is None

    asyncio.run(_run())


def test_resolve_denied_missing_user_header():
    """Missing user header → None."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            headers = {DEV_ORG_HEADER: str(uuid.uuid4())}
            auth = await resolve_auth_context(session, headers)
            assert auth is None

    asyncio.run(_run())


def test_resolve_denied_missing_org_header():
    """Missing org header → None."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            headers = {DEV_USER_HEADER: str(uuid.uuid4())}
            auth = await resolve_auth_context(session, headers)
            assert auth is None

    asyncio.run(_run())


def test_resolve_denied_non_dev_env(monkeypatch):
    """Outside development, dev headers are ignored entirely."""

    monkeypatch.setattr(
        "tender_compliance_api.auth.service.get_settings",
        lambda: Settings(app_env="production"),
    )

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            headers = {
                DEV_USER_HEADER: str(uuid.uuid4()),
                DEV_ORG_HEADER: str(uuid.uuid4()),
            }
            auth = await resolve_auth_context(session, headers)
            assert auth is None  # Not development → deny

    asyncio.run(_run())


def test_resolve_denied_invalid_uuid():
    """Non-UUID header values → None (no crash, no fabrication)."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            headers = {
                DEV_USER_HEADER: "not-a-uuid",
                DEV_ORG_HEADER: "alsonotauuid",
            }
            auth = await resolve_auth_context(session, headers)
            assert auth is None

    asyncio.run(_run())


def test_resolve_denied_cross_tenant_membership():
    """A user who is a member of Org A cannot resolve a context for Org B.

    This enforces the guardrail: "Never trust an organization ID supplied by
    the browser without verifying membership."
    """

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            user_id, org_a = await _create_dev_identity(session, role="owner")
            # A different user who is a member of a different org.
            _, org_b = await _create_dev_identity(
                session,
                user_id=uuid.uuid4(),
                org_id=uuid.uuid4(),
            )

            # User A (member of Org A only) tries to access Org B.
            headers = {
                DEV_USER_HEADER: str(user_id),
                DEV_ORG_HEADER: str(org_b),
            }
            auth = await resolve_auth_context(session, headers)
            assert auth is None  # No membership for Org B → denied

    asyncio.run(_run())


def test_resolve_dev_auto_creates_user_and_org():
    """In dev mode, unknown users and orgs are auto-created (but not
    memberships — absence of membership still denies access)."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            user_id = uuid.uuid4()
            org_id = uuid.uuid4()
            headers = {
                DEV_USER_HEADER: str(user_id),
                DEV_ORG_HEADER: str(org_id),
            }
            auth = await resolve_auth_context(session, headers)
            assert auth is None  # Created but no membership → denied

            # Verify the User and Organization were indeed created.
            user = await session.get(User, user_id)
            org = await session.get(Organization, org_id)
            assert user is not None
            assert user.auth_provider == "dev"
            assert org is not None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Cross-tenant scoping
# ---------------------------------------------------------------------------


def test_tenant_query_cannot_see_other_org():
    """A tenant-scoped query by auth.organization_id cannot return another
    organization's data, even when the caller knows the UUID."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            user_id, org_a = await _create_dev_identity(session, role="owner")

            # Org B exists in the database but is NOT in the auth context's
            # organization scope.
            org_b = uuid.uuid4()
            session.add(Organization(id=org_b, name="Org B"))
            await session.flush()

            headers = {
                DEV_USER_HEADER: str(user_id),
                DEV_ORG_HEADER: str(org_a),
            }
            auth = await resolve_auth_context(session, headers)
            assert auth is not None

            # A tenant-scoped query uses auth.organization_id — it can only
            # see the authenticated org.
            result = await session.execute(
                select(Organization).where(Organization.id == auth.organization_id)
            )
            visible = result.scalar_one()
            assert visible.id == org_a

            # Even if the caller tries to look up org_b by its UUID within
            # a tenant-scoped query, the org filter excludes it.
            result_b = await session.execute(
                select(Organization).where(
                    Organization.id == org_b,
                    Organization.id == auth.organization_id,
                )
            )
            assert result_b.scalars().first() is None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Dependency boundary — deny-by-default
# ---------------------------------------------------------------------------


def test_get_auth_context_raises_401_without_headers():
    """The FastAPI dependency raises 401 when no valid actor is present."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            request = _make_request({})
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(request, session)
            assert exc_info.value.status_code == 401

    asyncio.run(_run())


def test_get_auth_context_raises_401_cross_tenant():
    """The dependency denies when the user is not a member of the claimed org."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            user_id, _ = await _create_dev_identity(session, role="owner")

            # Claim an org the user is not a member of.
            headers = {
                DEV_USER_HEADER: str(user_id),
                DEV_ORG_HEADER: str(uuid.uuid4()),
            }
            request = _make_request(headers)
            with pytest.raises(HTTPException) as exc_info:
                await get_auth_context(request, session)
            assert exc_info.value.status_code == 401

    asyncio.run(_run())


def test_get_auth_context_returns_verified_context():
    """The dependency returns a verified AuthContext for valid dev headers."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            user_id, org_id = await _create_dev_identity(session, role="admin")
            headers = {
                DEV_USER_HEADER: str(user_id),
                DEV_ORG_HEADER: str(org_id),
            }
            request = _make_request(headers)
            auth = await get_auth_context(request, session)
            assert isinstance(auth, AuthContext)
            assert auth.actor_id == user_id
            assert auth.organization_id == org_id
            assert "admin" in auth.roles

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Audit service
# ---------------------------------------------------------------------------


def test_audit_event_written_and_flushed():
    """write_audit_event creates a row with an assigned ID (flushed)."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            user_id, org_id = await _create_dev_identity(session, role="owner")
            auth = AuthContext(
                actor_id=user_id, organization_id=org_id, roles=frozenset({"owner"})
            )
            event = await write_audit_event(
                session, auth, "identity.test",
                entity_type="User", entity_id=user_id, metadata={"detail": "ok"},
            )
            assert event.id is not None
            assert event.organization_id == org_id
            assert event.actor_id == user_id
            assert event.action == "identity.test"
            assert event.metadata_json == {"detail": "ok"}

    asyncio.run(_run())


def test_audit_events_org_scoped():
    """Audit events written under one org are not visible when querying
    another org's scope."""

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            # Org A + user A
            user_a, org_a = await _create_dev_identity(session, role="owner")
            # Org B + user B
            user_b, org_b = await _create_dev_identity(
                session,
                user_id=uuid.uuid4(),
                org_id=uuid.uuid4(),
                role="owner",
            )

            auth_a = AuthContext(
                actor_id=user_a, organization_id=org_a, roles=frozenset({"owner"})
            )
            auth_b = AuthContext(
                actor_id=user_b, organization_id=org_b, roles=frozenset({"owner"})
            )

            await write_audit_event(session, auth_a, "org_a.action")
            await write_audit_event(session, auth_b, "org_b.action")
            await session.commit()

            # Org A scope sees only its own event.
            a_result = await session.execute(
                select(AuditLog).where(AuditLog.organization_id == org_a)
            )
            a_actions = {e.action for e in a_result.scalars().all()}
            assert a_actions == {"org_a.action"}

            # Org B scope sees only its own event.
            b_result = await session.execute(
                select(AuditLog).where(AuditLog.organization_id == org_b)
            )
            b_actions = {e.action for e in b_result.scalars().all()}
            assert b_actions == {"org_b.action"}

            # The AuditService class path supports system actors too.
            svc = AuditService(session)
            system_event = await svc.log(
                organization_id=org_a,
                actor_id=None,
                actor_type="SYSTEM",
                action="system.check",
            )
            await session.commit()
            assert system_event.actor_id is None
            assert system_event.actor_type == "SYSTEM"

    asyncio.run(_run())



def test_single_workspace_bootstraps_owner_without_headers(monkeypatch):
    """Private-beta mode creates its one owner/org/membership on first request."""
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    monkeypatch.setattr(
        "tender_compliance_api.auth.service.get_settings",
        lambda: Settings(
            app_env="production",
            auth_mode="single_workspace",
            single_workspace_user_id=str(user_id),
            single_workspace_org_id=str(org_id),
            single_workspace_org_name="Pilot Workspace",
        ),
    )

    async def _run():
        async with asynccontextmanager(get_session)() as session:
            auth = await resolve_auth_context(session, {})
            assert auth is not None
            assert auth.actor_id == user_id
            assert auth.organization_id == org_id
            assert auth.roles == frozenset({"owner"})

            membership = (
                await session.execute(
                    select(Membership).where(
                        Membership.organization_id == org_id,
                        Membership.user_id == user_id,
                    )
                )
            ).scalar_one()
            assert membership.role == "owner"

            again = await resolve_auth_context(session, {})
            assert again == auth

    asyncio.run(_run())
