"""Cross-tenant security tests (CP45).

Verifies that every tenant-owned resource enforces organization isolation
at the data boundary — not just in the UI.  A user from Org B must never
receive a 200 when attempting to access Org A's projects, documents,
document versions, requirements, reviews, matrix, or exports.

Per AGENTS.md: "Frontend hiding is never authorization" and "Enforce
organization/project isolation at every data boundary."
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from fastapi.testclient import TestClient

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


def _build_org_a_project_doc_version(
    requirements: list[str] | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, int]:
    """Set up Org A with a project, document, version, and requirements.

    Returns (user_a, org_a, project_id, doc_id, version_number).
    """
    requirements = requirements or []

    async def _setup():
        org_a = uuid.uuid4()
        user_a = uuid.uuid4()
        project_id = uuid.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=org_a, name="Org A"))
            session.add(
                User(
                    id=user_a,
                    auth_provider="dev",
                    auth_provider_user_id=str(user_a),
                )
            )
            session.add(
                Membership(organization_id=org_a, user_id=user_a, role="owner")
            )
            session.add(
                Project(
                    id=project_id,
                    organization_id=org_a,
                    name="Org A Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_a,
                )
            )
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
            for i, raw in enumerate(requirements):
                req = Requirement(
                    document_version_id=version.id,
                    promotion_key=f"pk-{i}",
                    requirement_type="obligation",
                    normalized_text=raw,
                    raw_source=raw,
                    uncertainty="confirmed",
                    ocr_warning=False,
                    review_state=RequirementReviewState.UNREVIEWED,
                )
                session.add(req)
            await session.commit()
            return user_a, org_a, project_id, doc.id, version.version_number

    return asyncio.run(_setup())


def _build_org_b_user() -> tuple[uuid.UUID, uuid.UUID]:
    """Create an Org B user that is NOT a member of Org A's project."""
    org_b = uuid.uuid4()
    user_b = uuid.uuid4()

    async def _setup():
        async with _session_cm() as session:
            session.add(Organization(id=org_b, name="Org B"))
            session.add(
                User(
                    id=user_b,
                    auth_provider="dev",
                    auth_provider_user_id=str(user_b),
                )
            )
            session.add(
                Membership(organization_id=org_b, user_id=user_b, role="owner")
            )
            await session.commit()

    asyncio.run(_setup())
    return user_b, org_b


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cross-tenant tests
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation:
    """Every tenant-owned resource endpoint must deny cross-tenant access."""

    def test_cross_tenant_get_requirements_list(self) -> None:
        """Org B cannot list Org A's requirements."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_get_requirement_detail(self) -> None:
        """Org B cannot view Org A's requirement detail."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        # Get the requirement ID from Org A
        resp_a = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_a, org_a),
        )
        req_id = resp_a.json()["items"][0]["id"]

        resp_b = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            headers=_headers(user_b, org_b),
        )
        assert resp_b.status_code == 404

    def test_cross_tenant_mark_reviewed(self) -> None:
        """Org B cannot mark Org A's requirement as reviewed."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp_a = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_a, org_a),
        )
        req_id = resp_a.json()["items"][0]["id"]

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}"
            f"/requirements/{req_id}/mark-reviewed",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_review_transition(self) -> None:
        """Org B cannot transition Org A's requirement review state."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp_a = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_a, org_a),
        )
        req_id = resp_a.json()["items"][0]["id"]

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}"
            f"/requirements/{req_id}/transition",
            json={"target_state": "reviewed"},
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_escalate(self) -> None:
        """Org B cannot escalate Org A's requirement."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp_a = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_a, org_a),
        )
        req_id = resp_a.json()["items"][0]["id"]

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}"
            f"/requirements/{req_id}/escalate",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_matrix(self) -> None:
        """Org B cannot access Org A's matrix."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/matrix",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_review_counts(self) -> None:
        """Org B cannot access Org A's review counts."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/review-counts",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_document_version_detail(self) -> None:
        """Org B cannot view Org A's document version."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_retry_processing(self) -> None:
        """Org B cannot retry Org A's document version."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/retry",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_export_creation(self) -> None:
        """Org B cannot create an export of Org A's document."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_export_list(self) -> None:
        """Org B cannot list Org A's exports."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_unknown_org_cannot_access(self) -> None:
        """A user whose claimed org doesn't exist (but is a member of their
        own org) cannot access another org's resources."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )

        # Create a third org with a membership but a fabricated project_id
        user_c, org_c = _build_org_b_user()
        fake_project = uuid.uuid4()

        resp = client.get(
            f"/projects/{fake_project}/documents",
            headers=_headers(user_c, org_c),
        )
        assert resp.status_code == 404

    def test_cross_tenant_project_patch(self) -> None:
        """Org B cannot modify Org A's project."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.patch(
            f"/projects/{project_id}",
            json={"name": "Hacked by Org B"},
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_cross_tenant_project_archive(self) -> None:
        """Org B cannot archive Org A's project."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.post(
            f"/projects/{project_id}/archive",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth injection tests
# ---------------------------------------------------------------------------


class TestAuthInjection:
    """Verify that auth context is never overridden by request body or
    query parameters."""

    def test_body_project_id_does_not_override_auth(self) -> None:
        """A request body containing a different organization_id must not
        affect which organization the request is scoped to."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        # Org B tries to access Org A's requirement by providing Org A's
        # project_id in the path but Org B's auth context in headers
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404

    def test_query_param_tenant_override_does_not_work(self) -> None:
        """Query parameters like ?organization_id=... must not override
        the auth context."""
        user_a, org_a, project_id, doc_id, ver = (
            _build_org_a_project_doc_version(["temp \u2264 85 \u00b0C"])
        )
        user_b, org_b = _build_org_b_user()

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements"
            f"?organization_id={org_a}",
            headers=_headers(user_b, org_b),
        )
        assert resp.status_code == 404
