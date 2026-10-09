"""Tests for CP35 — Requirement list/detail API.

Covers:
- GET .../requirements (list): ordering, pagination, filters, empty results
- GET .../requirements/{id} (detail): includes constraints and sources
- Tenant isolation: cross-org access is denied
- No document body leakage in any response
- Stable ordering and pagination correctness
- CP39 fields (superseded, mandatory, display_order) on summary/detail
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.db.models import (
    DocumentPage,
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


class TestAddRequirementFromCoverageFinding:
    def _setup_source_page(
        self, project_id, *, text, ocr_needed=False, ocr_confidence=None, page_number=3
    ):
        async def _create():
            async with _session_cm() as session:
                doc = TenderDocument(
                    project_id=project_id, display_name="tender.pdf", document_type="tender"
                )
                session.add(doc)
                await session.flush()
                version = DocumentVersion(
                    document_id=doc.id, version_number=1, stored_object_id=uuid.uuid4(),
                    sha256="source-test", mime_type="application/pdf", size_bytes=10,
                    processing_status=DocumentProcessingStatus.PARSED,
                )
                session.add(version)
                await session.flush()
                session.add(DocumentPage(
                    document_version_id=version.id, page_number=page_number,
                    extracted_text=text, cleaned_text=text, ocr_needed=ocr_needed,
                    ocr_confidence=(
                        ocr_confidence
                        if ocr_confidence is not None
                        else (0.91 if ocr_needed else None)
                    ),
                ))
                await session.commit()
                return doc.id
        return asyncio.run(_create())

    def test_adds_exact_source_quote_and_is_idempotent(self):
        user_id, org_id, project_id = _build_org_project()
        quote = "The instrument shall include installation and operator training."
        doc_id = self._setup_source_page(project_id, text=f"Clause 4. {quote}")
        url = f"/projects/{project_id}/documents/{doc_id}/versions/1/requirements/from-source"
        payload = {"page_number": 3, "source_quote": quote, "requirement_type": "obligation"}
        first = client.post(url, json=payload, headers=_headers(user_id, org_id))
        second = client.post(url, json=payload, headers=_headers(user_id, org_id))
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["raw_source"] == quote
        assert first.json()["review_state"] == "unreviewed"
        source = first.json()["sources"][0]
        assert source["page_number"] == 3
        assert source["location_type"] == "exact"

    def test_same_finding_is_idempotent_when_reviewed_from_another_page(self):
        user_id, org_id, project_id = _build_org_project()
        quote = "The instrument shall include operator training."
        doc_id = self._setup_source_page(project_id, text=quote, page_number=3)

        async def _add_second_page():
            async with _session_cm() as session:
                version = (await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == doc_id,
                        DocumentVersion.version_number == 1,
                    )
                )).scalar_one()
                session.add(DocumentPage(
                    document_version_id=version.id,
                    page_number=4,
                    extracted_text=quote,
                    cleaned_text=quote,
                    ocr_needed=False,
                    ocr_confidence=None,
                ))
                await session.commit()

        asyncio.run(_add_second_page())
        url = f"/projects/{project_id}/documents/{doc_id}/versions/1/requirements/from-source"
        first = client.post(
            url,
            json={"page_number": 3, "source_quote": quote, "requirement_type": "obligation"},
            headers=_headers(user_id, org_id),
        )
        second = client.post(
            url,
            json={"page_number": 4, "source_quote": quote, "requirement_type": "obligation"},
            headers=_headers(user_id, org_id),
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["sources"][0]["page_number"] == 3

    def test_superseded_matching_finding_returns_conflict(self):
        user_id, org_id, project_id = _build_org_project()
        quote = "The instrument shall include operator training."
        doc_id = self._setup_source_page(project_id, text=quote)
        root = f"/projects/{project_id}/documents/{doc_id}/versions/1/requirements"
        payload = {"page_number": 3, "source_quote": quote, "requirement_type": "obligation"}
        added = client.post(f"{root}/from-source", json=payload, headers=_headers(user_id, org_id))
        assert added.status_code == 201, added.text
        superseded = client.post(
            f"{root}/{added.json()['id']}/supersede", headers=_headers(user_id, org_id)
        )
        assert superseded.status_code == 200, superseded.text
        retried = client.post(
            f"{root}/from-source",
            json=payload,
            headers=_headers(user_id, org_id),
        )
        assert retried.status_code == 409

    def test_rejects_quote_from_another_page(self):
        user_id, org_id, project_id = _build_org_project()
        doc_id = self._setup_source_page(project_id, text="A different source clause.")
        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/1/requirements/from-source",
            json={
                "page_number": 3,
                "source_quote": "Unsupported wording.",
                "requirement_type": "obligation",
            },
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 422

    def test_other_organization_cannot_add_requirement_to_version(self):
        _, _, project_id = _build_org_project()
        foreign_id, foreign_org_id, _ = _build_org_project()
        quote = "The instrument shall include training."
        doc_id = self._setup_source_page(project_id, text=quote)
        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/1/requirements/from-source",
            json={"page_number": 3, "source_quote": quote, "requirement_type": "obligation"},
            headers=_headers(foreign_id, foreign_org_id),
        )
        assert response.status_code == 404

    def test_ocr_source_remains_in_warning_state(self):
        user_id, org_id, project_id = _build_org_project()
        quote = "The instrument shall include training."
        doc_id = self._setup_source_page(project_id, text=quote, ocr_needed=True)
        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/1/requirements/from-source",
            json={"page_number": 3, "source_quote": quote, "requirement_type": "prohibition"},
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 201, response.text
        assert response.json()["review_state"] == "ocr_warning"
        assert response.json()["sources"][0]["location_type"] == "exact"

    def test_completed_ocr_keeps_ocr_warning_and_selected_deontic_type(self):
        user_id, org_id, project_id = _build_org_project()
        quote = "The supplier shall not use a substitute method."
        doc_id = self._setup_source_page(
            project_id, text=quote, ocr_needed=False, ocr_confidence=0.91
        )
        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/1/requirements/from-source",
            json={"page_number": 3, "source_quote": quote, "requirement_type": "prohibition"},
            headers=_headers(user_id, org_id),
        )
        assert response.status_code == 201, response.text
        assert response.json()["review_state"] == "ocr_warning"
        assert response.json()["requirement_type"] == "prohibition"


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


class TestCP39SummaryFields:
    """Verify CP39 fields appear on list/detail responses."""

    def test_summary_includes_cp39_fields(self):
        """List response includes display_order, mandatory, superseded after set."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver = _create_doc_version_with_requirements(
            project_id, [("obligation", "weight ≤ 2 kg")]
        )
        req_id = _get_first_req_id_str(doc_id, ver)

        # Set mandatory to True and display_order to 0.
        client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mandatory",
            json={"value": True},
            headers=_headers(user_id, org_id),
        )

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "superseded" in item
        assert item["superseded"] is False
        assert "mandatory" in item
        assert item["mandatory"] is True

    def test_detail_includes_cp39_fields(self):
        """Detail response includes superseded, notes, categories."""
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
        detail = resp.json()
        assert "superseded" in detail
        assert detail["superseded"] is False
        assert "notes" in detail
        assert "categories" in detail
        assert detail["notes"] == []
        assert detail["categories"] == []
