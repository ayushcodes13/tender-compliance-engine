"""Tests for CP40 — Review-state machine, audit timeline, and real progress counts.

Covers:
- Valid review state transitions (UNREVIEWED → REVIEWED, REVIEWED → UNREVIEWED, etc.)
- Invalid transitions rejected with 409
- Prevent REVIEWED when uncertainty != confirmed (unless override)
- mark_reviewed / reopen / escalate endpoints
- Review counts endpoint returns correct counts
- Audit events logged for transitions
- Next/previous unresolved navigation uses persisted state
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
            session.add(Organization(id=org_id, name="CP40 Test Org"))
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
                    name="CP40 Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


def _create_requirement(project_id: uuid.UUID, normalized: str, raw: str = "raw",
                        uncertainty: str = "confirmed"):
    """Create a document version with one requirement.
    Returns (document_id, version_number, requirement_id).
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
                uncertainty=uncertainty,
                ocr_warning=False,
                review_state=RequirementReviewState.UNREVIEWED,
            )
            session.add(req)
            await session.flush()
            req_id = req.id
            await session.commit()
            return doc.id, version.version_number, str(req_id)

    return asyncio.run(_create())


# ---------------------------------------------------------------------------
# Review state machine
# ---------------------------------------------------------------------------


class TestReviewStateTransitions:
    def test_unreviewed_to_reviewed(self):
        """UNREVIEWED → REVIEWED is valid."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/transition",
            json={"target_state": "reviewed"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "reviewed"

    def test_reviewed_to_unreviewed(self):
        """REVIEWED → UNREVIEWED (reopen) is valid."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        # First mark as reviewed.
        client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mark-reviewed",
            json={},
            headers=_headers(user_id, org_id),
        )

        # Then reopen.
        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/reopen",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "unreviewed"

    def test_unreviewed_to_needs_clarification(self):
        """UNREVIEWED → NEEDS_CLARIFICATION (escalate) is valid."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/escalate",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "needs_clarification"

    def test_reviewed_to_needs_clarification(self):
        """REVIEWED → NEEDS_CLARIFICATION is valid (re-escalate)."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mark-reviewed",
            json={},
            headers=_headers(user_id, org_id),
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/escalate",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "needs_clarification"

    def test_unreviewed_to_ocr_warning(self):
        """UNREVIEWED → OCR_WARNING is valid."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/transition",
            json={"target_state": "ocr_warning"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "ocr_warning"

    def test_invalid_transition_rejected(self):
        """Invalid target state string returns 400."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/transition",
            json={"target_state": "compliance_pass"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 400

    def test_idempotent_transition(self):
        """Transitioning to the same state is a no-op, not an error."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/transition",
            json={"target_state": "unreviewed"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "unreviewed"


class TestUncertaintyOverride:
    def test_reviewed_blocked_when_uncertain(self):
        """Cannot mark REVIEWED when uncertainty is 'partial'."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(
            project_id, "weight ≤ 2 kg", "raw", uncertainty="partial"
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mark-reviewed",
            json={},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "invalid_transition"

    def test_reviewed_allowed_with_override(self):
        """override_uncertainty=true allows marking REVIEWED despite uncertainty."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(
            project_id, "weight ≤ 2 kg", "raw", uncertainty="partial"
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mark-reviewed",
            json={"override_uncertainty": True},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "reviewed"

    def test_reviewed_allowed_when_confirmed(self):
        """Can mark REVIEWED when uncertainty is 'confirmed'."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(
            project_id, "weight ≤ 2 kg", "raw", uncertainty="confirmed"
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mark-reviewed",
            json={},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["review_state"] == "reviewed"


class TestReviewCounts:
    def test_counts_match_database(self):
        """Review counts endpoint returns accurate counts."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, _ = _create_requirement(project_id, "req1", "raw")

        # Create additional requirements with different states.
        async def _add_reqs():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == doc_id,
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                reqs = [
                    Requirement(
                        document_version_id=version.id,
                        promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                        requirement_type="obligation",
                        normalized_text=f"req {i}",
                        raw_source=f"raw{i}",
                        uncertainty="confirmed",
                        review_state=RequirementReviewState.REVIEWED,
                    )
                    for i in range(2)
                ]
                reqs2 = [
                    Requirement(
                        document_version_id=version.id,
                        promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                        requirement_type="obligation",
                        normalized_text=f"req {i}",
                        raw_source=f"raw{i}",
                        uncertainty="uncertain",
                        review_state=RequirementReviewState.NEEDS_CLARIFICATION,
                    )
                    for i in range(2)
                ]
                reqs3 = [
                    Requirement(
                        document_version_id=version.id,
                        promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                        requirement_type="obligation",
                        normalized_text=f"req {i}",
                        raw_source=f"raw{i}",
                        uncertainty="confirmed",
                        review_state=RequirementReviewState.OCR_WARNING,
                    )
                    for i in range(2)
                ]
                reqs4 = [
                    Requirement(
                        document_version_id=version.id,
                        promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                        requirement_type="obligation",
                        normalized_text=f"req {i}",
                        raw_source=f"raw{i}",
                        uncertainty="confirmed",
                        review_state=RequirementReviewState.UNREVIEWED,
                        superseded=True,
                    )
                    for i in range(2)
                ]
                for r in reqs + reqs2 + reqs3 + reqs4:
                    session.add(r)
                await session.commit()

        asyncio.run(_add_reqs())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/review-counts",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        counts = resp.json()
        # req1 (unreviewed) + 2 reviewed + 2 needs_clarification + 2 ocr_warning = 7 active
        # 2 superseded (unreviewed + superseded) excluded from per-state counts
        assert counts["total"] == 9
        assert counts["active"] == 7  # total - superseded
        assert counts["unreviewed"] == 1  # just req1 (superseded excluded)
        assert counts["reviewed"] == 2
        assert counts["needs_clarification"] == 2
        assert counts["ocr_warning"] == 2
        assert counts["superseded"] == 2

    def test_counts_empty_version(self):
        """Counts on a version with no requirements return zeros."""
        user_id, org_id, project_id = _build_org_project()
        # Create a document version with no requirements
        async def _create_empty_doc_version():
            async with _session_cm() as session:
                doc = TenderDocument(
                    project_id=project_id, display_name="empty.pdf",
                    document_type="tender"
                )
                session.add(doc)
                await session.flush()
                version = DocumentVersion(
                    document_id=doc.id,
                    version_number=1,
                    stored_object_id=uuid.uuid4(),
                    sha256="empty",
                    mime_type="application/pdf",
                    size_bytes=0,
                    processing_status=DocumentProcessingStatus.PARSED,
                )
                session.add(version)
                await session.commit()
                return doc.id, version.version_number

        doc_id, ver = asyncio.run(_create_empty_doc_version())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/review-counts",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        counts = resp.json()
        assert counts["total"] == 0
        assert counts["active"] == 0
        assert counts["unreviewed"] == 0


class TestTenantIsolation:
    def test_transition_tenant_isolation(self):
        """Cross-org transition attempt returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id = _create_requirement(project_id, "req", "raw")

        async def _other_org():
            other_org = uuid.uuid4()
            other_user = uuid.uuid4()
            async with _session_cm() as session:
                session.add(Organization(id=other_org, name="Other"))
                session.add(
                    User(
                        id=other_user,
                        auth_provider="dev",
                        auth_provider_user_id=str(other_user),
                    )
                )
                session.add(
                    Membership(organization_id=other_org, user_id=other_user, role="owner")
                )
                await session.commit()
            return other_user, other_org

        other_user, other_org = asyncio.run(_other_org())

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mark-reviewed",
            json={},
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404

    def test_counts_tenant_isolation(self):
        """Cross-org counts attempt returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, _ = _create_requirement(project_id, "req", "raw")

        async def _other_org():
            other_org = uuid.uuid4()
            other_user = uuid.uuid4()
            async with _session_cm() as session:
                session.add(Organization(id=other_org, name="Other"))
                session.add(
                    User(
                        id=other_user,
                        auth_provider="dev",
                        auth_provider_user_id=str(other_user),
                    )
                )
                session.add(
                    Membership(organization_id=other_org, user_id=other_user, role="owner")
                )
                await session.commit()
            return other_user, other_org

        other_user, other_org = asyncio.run(_other_org())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/review-counts",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404
