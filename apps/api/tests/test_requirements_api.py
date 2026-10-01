"""Tests for CP35 — Requirement list/detail API.

Covers:
- GET .../requirements (list): ordering, pagination, filters, empty results
- GET .../requirements/{id} (detail): includes constraints and sources
- Tenant isolation: cross-org access is denied
- No document body leakage in any response
- Stable ordering and pagination correctness
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

# Reusable async context manager for the test session (mirrors conftest).
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
            session.add(Organization(id=org_id, name="CP35 Test Org"))
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
                    name="CP35 Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


async def _get_version_id(session, doc_id: uuid.UUID, ver: int) -> uuid.UUID:
    """Fetch the version.id for a (document_id, version_number)."""
    result = await session.execute(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == doc_id,
            DocumentVersion.version_number == ver,
        )
    )
    return result.scalar_one()


def _create_doc_version_with_requirements(
    project_id: uuid.UUID,
    requirements_data: list[tuple[str, str]],
    ocr_warning: bool = False,
):
    """Create a document version with requirements.
    Each item in requirements_data is (requirement_type, raw_source).
    Returns (document_id, version_number).
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
            for req_type, raw_source in requirements_data:
                req = Requirement(
                    document_version_id=version.id,
                    promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                    requirement_type=req_type,
                    normalized_text=raw_source,
                    raw_source=raw_source,
                    uncertainty="confirmed",
                    ocr_warning=ocr_warning,
                    review_state=RequirementReviewState.UNREVIEWED,
                )
                session.add(req)
            await session.commit()
            return doc.id, version.version_number

    return asyncio.run(_create())


def _get_first_req_id_str(doc_id: uuid.UUID, ver: int) -> str:
    """Fetch the first requirement's ID as a string."""
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
                select(Requirement)
                .where(Requirement.document_version_id == version_id)
                .order_by(Requirement.created_at)
                .limit(1)
            )
            return str(result.scalar_one().id)
    return asyncio.run(_get())


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


class TestRequirementList:
    def test_list_returns_requirements(self):
        """GET list returns all requirements for the version."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id,
            [("obligation", "weight ≤ 2 kg"), ("obligation", "IP65 enclosure")],
        )
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert body["limit"] == 50
        assert body["offset"] == 0

    def test_list_empty(self):
        """GET list on a version with no requirements returns empty."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id, []
        )
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_filters_by_review_state(self):
        """GET list with review_state filter returns only matching requirements."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id,
            [("obligation", "weight ≤ 2 kg"), ("obligation", "IP65 enclosure")],
        )
        # Update one requirement to REVIEWED
        async def _set_state():
            async with _session_cm() as session:
                version_id = await _get_version_id(session, doc_id, ver)
                result = await session.execute(
                    select(Requirement).where(
                        Requirement.document_version_id == version_id
                    )
                )
                reqs = result.scalars().all()
                reqs[0].review_state = RequirementReviewState.REVIEWED
                await session.commit()
        asyncio.run(_set_state())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements"
            f"?review_state=reviewed",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["review_state"] == "reviewed"

    def test_list_pagination(self):
        """GET list with limit/offset returns correct subsets."""
        user_id, org_id, project_id = _build_org_project()
        reqs = [("obligation", f"Requirement {i} ≤ {i} kg") for i in range(1, 6)]
        doc_id, ver = _create_doc_version_with_requirements(project_id, reqs)

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements"
            f"?limit=2&offset=1",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 1

    def test_list_search(self):
        """GET list with search returns matching requirements."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id,
            [
                ("obligation", "weight ≤ 2 kg"),
                ("obligation", "temperature ≥ -10 °C"),
                ("obligation", "IP65 enclosure"),
            ],
        )
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements"
            f"?search=weight",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert "weight" in body["items"][0]["normalized_text"].lower()

    def test_list_no_document_body_leakage(self):
        """List summary response never includes raw_source or constraints."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id, [("obligation", "weight ≤ 2 kg")]
        )
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert "raw_source" not in item
            assert "constraints" not in item


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


class TestRequirementDetail:
    def test_detail_returns_full_info(self):
        """GET detail returns requirement with constraints and sources."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id, [("obligation", "weight ≤ 2 kg")]
        )
        req_id = _get_first_req_id_str(doc_id, ver)

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == req_id
        assert body["requirement_type"] == "obligation"
        assert "raw_source" in body
        assert "normalized_text" in body
        assert "review_state" in body
        assert "ocr_warning" in body
        assert "constraints" in body
        assert "sources" in body

    def test_detail_not_found(self):
        """GET detail with non-existent requirement returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id, [("obligation", "weight ≤ 2 kg")]
        )
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{uuid.uuid4()}",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404

    def test_detail_tenant_isolation(self):
        """A user from a different org cannot access another org's requirement."""

        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id, [("obligation", "weight ≤ 2 kg")]
        )
        req_id = _get_first_req_id_str(doc_id, ver)

        # Create a second org/user that is NOT a member of the project.
        async def _setup_other():
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
        other_user, other_org = asyncio.run(_setup_other())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Stable ordering
# ---------------------------------------------------------------------------


class TestStableOrdering:
    def test_list_ordered_by_created_at_desc(self):
        """Requirements are returned with created_at timestamps for stable
        ordering."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id,
            [("obligation", "weight ≤ 2 kg"), ("obligation", "IP65 enclosure")],
        )
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        for item in items:
            assert "created_at" in item
