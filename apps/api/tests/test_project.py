"""Tests for the Project domain service (CP09).

Covers:
- Project creation in DRAFT status with audit event and creator.
- Tenant-scoped get/list — Org A cannot see Org B's projects.
- Lifecycle: rename, archive, reopen with transition guards.
- Cross-tenant denial for mutations.
- Audit events carry project_id and are organization-scoped.
- Projects survive restart (file-based DB persistence).
"""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    AuditLog,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    User,
)
from tender_compliance_api.project import (
    ProjectArchivedError,
    ProjectNotFoundError,
    ProjectService,
    StateTransitionError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_auth(org_id: uuid.UUID, user_id: uuid.UUID) -> AuthContext:
    """Build a minimal verified AuthContext (owner role)."""
    return AuthContext(
        actor_id=user_id,
        organization_id=org_id,
        roles=frozenset({"owner"}),
    )


async def _create_dev_identity(session, role: str = "owner") -> AuthContext:
    """Create org + user + membership (dev convenience).  Returns AuthContext."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session.add(Organization(id=org_id, name=f"Org {org_id}"))
    session.add(
        User(id=user_id, auth_provider="dev", auth_provider_user_id=str(user_id))
    )
    session.add(Membership(organization_id=org_id, user_id=user_id, role=role))
    await session.flush()
    return _make_auth(org_id, user_id)


async def _create_project(session, auth: AuthContext, name: str = "Tender Project",
                          external_tender_id: str | None = None) -> Project:
    """Create a project via the service (starts in DRAFT)."""
    svc = ProjectService(session)
    return await svc.create(auth, name=name, external_tender_id=external_tender_id)


async def _audit_actions(session, *, project_id: uuid.UUID | None = None) -> list[str]:
    """Return sorted action strings from the audit log, optionally filtered."""
    stmt = select(AuditLog.action)
    if project_id is not None:
        stmt = stmt.where(AuditLog.project_id == project_id)
    result = await session.execute(stmt)
    return sorted(row[0] for row in result)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_create_project_in_draft_status(session_cm):
    """A new project starts in DRAFT, records creator + audit event."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            svc = ProjectService(session)
            project = await svc.create(
                auth, name="Tender 2024-01", external_tender_id="TEND-001"
            )

            assert project.id is not None
            assert project.organization_id == auth.organization_id
            assert project.name == "Tender 2024-01"
            assert project.external_tender_id == "TEND-001"
            assert project.status == ProjectStatus.DRAFT
            assert project.created_by == auth.actor_id

            # Audit event recorded with project scope
            actions = await _audit_actions(session, project_id=project.id)
            assert actions == ["project.create"]

    asyncio.run(_run())


def test_create_default_no_external_tender_id(session_cm):
    """external_tender_id is nullable and defaults to None."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Basic")

            assert project.external_tender_id is None
            assert project.status == ProjectStatus.DRAFT

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Read / tenant scoping
# ---------------------------------------------------------------------------


def test_get_project_tenant_scoped(session_cm):
    """Org A can read its project; Org B cannot (returns None)."""

    async def _run():
        async with session_cm() as session:
            auth_a = await _create_dev_identity(session)
            auth_b = await _create_dev_identity(session)

            svc_a = ProjectService(session)
            svc_b = ProjectService(session)
            project = await svc_a.create(auth_a, name="A's project")

            # Owner can read it
            mine = await svc_a.get(auth_a, project.id)
            assert mine is not None
            assert mine.id == project.id

            # Org B cannot read it even with the correct UUID
            other = await svc_b.get(auth_b, project.id)
            assert other is None

    asyncio.run(_run())


def test_list_projects_tenant_scoped(session_cm):
    """Each org sees only its own projects."""

    async def _run():
        async with session_cm() as session:
            auth_a = await _create_dev_identity(session)
            auth_b = await _create_dev_identity(session)

            svc_a = ProjectService(session)
            svc_b = ProjectService(session)
            await svc_a.create(auth_a, name="A1")
            await svc_a.create(auth_a, name="A2")
            await svc_b.create(auth_b, name="B1")

            projects_a = await svc_a.list(auth_a)
            assert {p.name for p in projects_a} == {"A1", "A2"}

            projects_b = await svc_b.list(auth_b)
            assert {p.name for p in projects_b} == {"B1"}

    asyncio.run(_run())


def test_get_nonexistent_project_returns_none(session_cm):
    """A UUID that does not exist in the org is not found."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            svc = ProjectService(session)
            result = await svc.get(auth, uuid.uuid4())
            assert result is None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Lifecycle: rename
# ---------------------------------------------------------------------------


def test_rename_project(session_cm):
    """Rename succeeds for a non-archived project; audit event recorded."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Original")
            svc = ProjectService(session)

            renamed = await svc.rename(auth, project.id, "New Name")
            assert renamed.name == "New Name"
            assert renamed.status == ProjectStatus.DRAFT  # status unchanged

            actions = await _audit_actions(session, project_id=project.id)
            assert "project.rename" in actions

    asyncio.run(_run())


def test_rename_archived_raises(session_cm):
    """Cannot rename an archived project without reopening first."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Active")
            svc = ProjectService(session)

            await svc.archive(auth, project.id)
            with pytest.raises(ProjectArchivedError):
                await svc.rename(auth, project.id, "Hacked")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Lifecycle: archive
# ---------------------------------------------------------------------------


def test_archive_project(session_cm):
    """Archive moves a project to ARCHIVED; audit event recorded."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Active")
            svc = ProjectService(session)

            archived = await svc.archive(auth, project.id)
            assert archived.status == ProjectStatus.ARCHIVED

            actions = await _audit_actions(session, project_id=project.id)
            assert "project.archive" in actions

    asyncio.run(_run())


def test_archive_already_archived_raises(session_cm):
    """Archiving an already-archived project raises StateTransitionError."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Active")
            svc = ProjectService(session)

            await svc.archive(auth, project.id)
            with pytest.raises(StateTransitionError):
                await svc.archive(auth, project.id)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Lifecycle: reopen
# ---------------------------------------------------------------------------


def test_reopen_project(session_cm):
    """Reopen resets status from ARCHIVED back to DRAFT."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Active")
            svc = ProjectService(session)

            await svc.archive(auth, project.id)
            reopened = await svc.reopen(auth, project.id)
            assert reopened.status == ProjectStatus.DRAFT

            actions = await _audit_actions(session, project_id=project.id)
            assert "project.reopen" in actions

    asyncio.run(_run())


def test_reopen_non_archived_raises(session_cm):
    """Cannot reopen a project that is not archived."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Active")
            svc = ProjectService(session)

            with pytest.raises(StateTransitionError):
                await svc.reopen(auth, project.id)

    asyncio.run(_run())


def test_archive_then_reopen_roundtrip(session_cm):
    """Full archive -> reopen cycle returns to DRAFT."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            project = await _create_project(session, auth, name="Lifecycle")
            svc = ProjectService(session)

            assert project.status == ProjectStatus.DRAFT

            await svc.archive(auth, project.id)
            project = await svc.get(auth, project.id)
            assert project is not None
            assert project.status == ProjectStatus.ARCHIVED

            reopened = await svc.reopen(auth, project.id)
            assert reopened.status == ProjectStatus.DRAFT

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Cross-tenant denial
# ---------------------------------------------------------------------------


def test_cross_tenant_cannot_archive(session_cm):
    """Org B cannot archive Org A's project."""

    async def _run():
        async with session_cm() as session:
            auth_a = await _create_dev_identity(session)
            auth_b = await _create_dev_identity(session)

            project = await _create_project(session, auth_a, name="A's project")
            svc_b = ProjectService(session)

            with pytest.raises(ProjectNotFoundError):
                await svc_b.archive(auth_b, project.id)

            # Verify Org A's project is unaffected
            svc_a = ProjectService(session)
            still_active = await svc_a.get(auth_a, project.id)
            assert still_active is not None
            assert still_active.status == ProjectStatus.DRAFT

    asyncio.run(_run())


def test_cross_tenant_cannot_rename(session_cm):
    """Org B cannot rename Org A's project."""

    async def _run():
        async with session_cm() as session:
            auth_a = await _create_dev_identity(session)
            auth_b = await _create_dev_identity(session)

            project = await _create_project(session, auth_a, name="A's project")
            svc_b = ProjectService(session)

            with pytest.raises(ProjectNotFoundError):
                await svc_b.rename(auth_b, project.id, "Hacked")

            # Original name preserved
            svc_a = ProjectService(session)
            still_original = await svc_a.get(auth_a, project.id)
            assert still_original is not None
            assert still_original.name == "A's project"

    asyncio.run(_run())


def test_cross_tenant_cannot_reopen(session_cm):
    """Org B cannot reopen Org A's archived project."""

    async def _run():
        async with session_cm() as session:
            auth_a = await _create_dev_identity(session)
            auth_b = await _create_dev_identity(session)

            project = await _create_project(session, auth_a, name="A's project")
            svc_a = ProjectService(session)
            svc_b = ProjectService(session)

            await svc_a.archive(auth_a, project.id)

            with pytest.raises(ProjectNotFoundError):
                await svc_b.reopen(auth_b, project.id)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Audit scoping
# ---------------------------------------------------------------------------


def test_audit_events_project_scoped(session_cm):
    """All mutation audit events carry the correct project_id."""

    async def _run():
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            svc = ProjectService(session)
            project = await svc.create(auth, name="Audited")
            await svc.rename(auth, project.id, "Renamed")
            await svc.archive(auth, project.id)

            actions = await _audit_actions(session, project_id=project.id)
            assert actions == [
                "project.archive",
                "project.create",
                "project.rename",
            ]

    asyncio.run(_run())


def test_audit_events_org_scoped(session_cm):
    """Audit events from different orgs are isolated."""

    async def _run():
        async with session_cm() as session:
            auth_a = await _create_dev_identity(session)
            auth_b = await _create_dev_identity(session)

            svc_a = ProjectService(session)
            svc_b = ProjectService(session)
            await svc_a.create(auth_a, name="A1")
            await svc_b.create(auth_b, name="B1")

            a_result = await session.execute(
                select(AuditLog).where(
                    AuditLog.organization_id == auth_a.organization_id
                )
            )
            b_result = await session.execute(
                select(AuditLog).where(
                    AuditLog.organization_id == auth_b.organization_id
                )
            )
            a_actions = {e.action for e in a_result.scalars().all()}
            b_actions = {e.action for e in b_result.scalars().all()}
            assert a_actions == {"project.create"}
            assert b_actions == {"project.create"}

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_project_survives_restart(session_cm):
    """A committed project persists across session boundaries."""

    async def _run():
        # --- First session: create + commit ---
        async with session_cm() as session:
            auth = await _create_dev_identity(session)
            svc = ProjectService(session)
            project = await svc.create(
                auth, name="Survivor", external_tender_id="TEND-999"
            )
            await session.commit()
            project_id = project.id
            org_id = auth.organization_id
            user_id = auth.actor_id

        # --- Second session: read back ---
        async with session_cm() as session:
            auth2 = AuthContext(
                actor_id=user_id,
                organization_id=org_id,
                roles=frozenset({"owner"}),
            )
            svc2 = ProjectService(session)
            loaded = await svc2.get(auth2, project_id)

            assert loaded is not None
            assert loaded.name == "Survivor"
            assert loaded.external_tender_id == "TEND-999"
            assert loaded.status == ProjectStatus.DRAFT

    asyncio.run(_run())
