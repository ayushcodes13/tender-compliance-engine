"""Tests for CP38 — Requirement edit and immutable revision history.

Covers:
- PATCH .../requirements/{id} — successful edit creates revision, preserves raw_source
- PATCH with same text — no revision created (no-op)
- PATCH with stale expected_updated_at — 409 Conflict (concurrent edit)
- PATCH for non-existent requirement — 404
- Tenant isolation — cross-org edit denied
- Revision history visible in detail response
- Raw source is never modified by edit
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    Requirement,
    RequirementReviewState,
    RequirementRevision,
    TenderDocument,
    User,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.main import app

client = TestClient(app)

_session_cm = contextlib.asynccontextmanager(get_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _build_org_project():
    """Set up org + user + membership + project; return (user_id, org_id, project_id)."""

    async def _setup():
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=org_id, name="CP38 Test Org"))
            session.add(
                User(
                    id=user_id,
                    auth_provider="dev",
                    auth_provider_user_id=str(user_id),
                )
            )
            session.add(
                Membership(organization_id=org_id, user_id=user_id, role="owner")
            )
            session.add(
                Project(
                    id=project_id,
                    organization_id=org_id,
                    name="CP38 Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


def _create_requirement(project_id: uuid.UUID, normalized: str, raw: str = "raw"):
    """Create a document version with one requirement.
    Returns (document_id, version_number, requirement_id, updated_at_str).
    """

    async def _create():
        async with _session_cm() as session:
            doc = TenderDocument(
                project_id=project_id,
                display_name="tender.pdf",
                document_type="tender",
            )
            session.add(doc)
            await session.flush()
            version = DocumentVersion(
                document_id=doc.id,
                version_number=1,
                stored_object_id=uuid.uuid4(),
                sha256="abc123",
                mime_type="application/pdf",
                size_bytes=1024,
                processing_status=DocumentProcessingStatus.PARSED,
            )
            session.add(version)
            await session.flush()
            req = Requirement(
                document_version_id=version.id,
                promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                requirement_type="obligation",
                normalized_text=normalized,
                raw_source=raw,
                uncertainty="confirmed",
                ocr_warning=False,
                review_state=RequirementReviewState.UNREVIEWED,
            )
            session.add(req)
            await session.flush()
            created_at = req.created_at.isoformat()
            await session.commit()
            return doc.id, version.version_number, str(req.id), created_at

    return asyncio.run(_create())


def _get_requirement_updated_at(doc_id: uuid.UUID, ver: int, req_id: str):
    """Fetch the current updated_at and raw_source of a requirement."""
    async def _get():
        async with _session_cm() as session:
            result = await session.execute(
                select(DocumentVersion.id).where(
                    DocumentVersion.document_id == doc_id,
                    DocumentVersion.version_number == ver,
                )
            )
            version_id = result.scalar_one()
            result = await session.execute(
                select(Requirement).where(
                    Requirement.id == uuid.UUID(req_id),
                    Requirement.document_version_id == version_id,
                )
            )
            req = result.scalar_one()
            return req.updated_at, req.raw_source

    return asyncio.run(_get())


def _count_revisions(req_id: str) -> int:
    """Count revision rows for a requirement."""
    async def _count():
        async with _session_cm() as session:
            result = await session.execute(
                select(RequirementRevision).where(
                    RequirementRevision.requirement_id == uuid.UUID(req_id)
                )
            )
            return len(result.scalars().all())

    return asyncio.run(_count())


def _setup_other_org():
    """Create a second org/user not in the project's org; return (user_id, org_id)."""
    async def _setup():
        other_org = uuid.uuid4()
        other_user = uuid.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=other_org, name="Other Org"))
            session.add(
                User(
                    id=other_user,
                    auth_provider="dev",
                    auth_provider_user_id=str(other_user),
                )
            )
            session.add(
                Membership(
                    organization_id=other_org, user_id=other_user, role="owner"
                )
            )
            await session.commit()
        return other_user, other_org

    return asyncio.run(_setup())


# ---------------------------------------------------------------------------
# Edit endpoint
# ---------------------------------------------------------------------------


class TestEditRequirement:
    def test_edit_creates_revision_and_preserves_raw_source(self):
        """PATCH edit creates a revision row and does not modify raw_source."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, created_at = _create_requirement(
            project_id, "weight ≤ 2 kg", "weight ≤ 2 kg"
        )

        # Get current updated_at
        updated_at, raw_before = _get_requirement_updated_at(doc_id, ver, req_id)

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            json={
                "normalized_text": "weight shall be ≤ 2 kg",
                "expected_updated_at": updated_at.isoformat() if updated_at else None,
                "note": "clarify wording",
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["normalized_text"] == "weight shall be ≤ 2 kg"
        # raw_source must be unchanged
        assert body["raw_source"] == "weight ≤ 2 kg"
        assert body["raw_source"] == raw_before
        # Revision history should now have 1 entry
        assert len(body["revisions"]) == 1
        rev = body["revisions"][0]
        assert rev["previous_normalized_text"] == "weight ≤ 2 kg"
        assert rev["note"] == "clarify wording"

    def test_edit_same_text_is_noop(self):
        """PATCH with identical text creates no revision."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, created_at = _create_requirement(
            project_id, "weight ≤ 2 kg", "weight ≤ 2 kg"
        )

        updated_at, _ = _get_requirement_updated_at(doc_id, ver, req_id)

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            json={
                "normalized_text": "weight ≤ 2 kg",
                "expected_updated_at": updated_at.isoformat() if updated_at else None,
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert len(resp.json()["revisions"]) == 0
        assert _count_revisions(req_id) == 0

    def test_edit_stale_timestamp_returns_409(self):
        """PATCH with a stale expected_updated_at returns 409 Conflict."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, created_at = _create_requirement(
            project_id, "weight ≤ 2 kg", "weight ≤ 2 kg"
        )

        # Use a timestamp from the past (before the requirement existed).
        stale = "2020-01-01T00:00:00"

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            json={
                "normalized_text": "weight shall be ≤ 2 kg",
                "expected_updated_at": stale,
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 409
        err = resp.json()
        assert "concurrent_edit" in err["detail"]["error"]
        assert "current_updated_at" in err["detail"]

    def test_edit_nonexistent_requirement(self):
        """PATCH for a non-existent requirement returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(
            project_id, "weight ≤ 2 kg", "weight ≤ 2 kg"
        )

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{uuid.uuid4()}",
            json={"normalized_text": "new text"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404

    def test_edit_tenant_isolation(self):
        """Cross-org edit attempt returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(
            project_id, "weight ≤ 2 kg", "weight ≤ 2 kg"
        )

        other_user, other_org = _setup_other_org()

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            json={"normalized_text": "malicious edit"},
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404
        # Verify the requirement was NOT modified.
        updated_at, raw = _get_requirement_updated_at(doc_id, ver, req_id)
        assert raw == "weight ≤ 2 kg"

    def test_raw_source_never_changes_after_edit(self):
        """Multiple edits do not change raw_source."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(
            project_id, "weight ≤ 2 kg", "weight ≤ 2 kg"
        )

        # First edit
        updated_at, _ = _get_requirement_updated_at(doc_id, ver, req_id)
        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            json={
                "normalized_text": "weight shall be ≤ 2 kg",
                "expected_updated_at": updated_at.isoformat() if updated_at else None,
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body1 = resp.json()
        assert body1["raw_source"] == "weight ≤ 2 kg"

        # Second edit (use the updated_at from first edit result)
        # Re-fetch from DB since the API response may not include updated_at
        updated_at2, raw2 = _get_requirement_updated_at(doc_id, ver, req_id)
        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            json={
                "normalized_text": "weight must be ≤ 2 kg",
                "expected_updated_at": updated_at2.isoformat() if updated_at2 else None,
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body2 = resp.json()
        assert body2["raw_source"] == "weight ≤ 2 kg"
        # Two revisions should exist
        assert len(body2["revisions"]) == 2
        assert _count_revisions(req_id) == 2
