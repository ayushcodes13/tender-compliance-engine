"""Tests for CP41 — Canonical Phase 1 matrix projection.

Covers:
- Projection returns all non-superseded requirements in display_order
- Superseded rows are excluded from the projection
- Null metadata (no sources, no categories, no notes) represented honestly
- Multi-source requirements: lowest page number used
- Multi-category requirements: first by display_order used
- Ordering: display_order NULLS LAST, then created_at desc, then id
- Tenant isolation on the matrix endpoint
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.db.models import (
    Category,
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    Requirement,
    RequirementReviewState,
    RequirementSource,
    TenderDocument,
    User,
    requirement_categories,
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
            session.add(Organization(id=org_id, name="CP41 Test Org"))
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
                    name="CP41 Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_id,
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
            await session.commit()
            return user_id, org_id, project_id, str(doc.id), version.version_number

    return asyncio.run(_setup())


def _add_requirement(
    session, version_id: uuid.UUID, normalized: str,
    display_order: int | None = None,
    mandatory: bool | None = None,
    review_state: RequirementReviewState = RequirementReviewState.UNREVIEWED,
    superseded: bool = False,
    clause: str | None = None,
    uncertainty: str = "confirmed",
) -> Requirement:
    """Helper to create a requirement in an existing session."""
    req = Requirement(
        document_version_id=version_id,
        promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
        requirement_type="obligation",
        normalized_text=normalized,
        raw_source=f"raw_{normalized}",
        uncertainty=uncertainty,
        ocr_warning=False,
        review_state=review_state,
        display_order=display_order,
        mandatory=mandatory,
        superseded=superseded,
        clause_number=clause,
    )
    session.add(req)
    return req


# ---------------------------------------------------------------------------
# Projection function tests
# ---------------------------------------------------------------------------


class TestMatrixProjection:
    def test_excludes_superseded(self):
        """Superseded requirements are not in the projection."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                _add_requirement(session, version.id, "req1", display_order=1)
                _add_requirement(session, version.id, "req2", display_order=2, superseded=True)
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import project_matrix_rows

        async def _project():
            async with _session_cm() as session:
                vres = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                v = vres.scalar_one()
                return await project_matrix_rows(session, v.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        assert rows[0].tender_requirement == "raw_req1"
        assert rows[0].serial == 1

    def test_preserves_display_order(self):
        """Rows are ordered by display_order ASC NULLS LAST."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                _add_requirement(session, version.id, "third", display_order=3)
                _add_requirement(session, version.id, "first", display_order=1)
                _add_requirement(session, version.id, "second", display_order=2)
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import project_matrix_rows

        async def _project():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                return await project_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert [r.tender_requirement for r in rows] == [
            "raw_first", "raw_second", "raw_third"
        ]
        assert [r.serial for r in rows] == [1, 2, 3]

    def test_null_display_order_sorted_last(self):
        """Requirements with NULL display_order sort after defined ones."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                _add_requirement(session, version.id, "no_order", display_order=None)
                _add_requirement(session, version.id, "ordered", display_order=1)
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import project_matrix_rows

        async def _project():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                return await project_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert rows[0].tender_requirement == "raw_ordered"
        assert rows[1].tender_requirement == "raw_no_order"

    def test_missing_metadata_represented_honestly(self):
        """Requirements without sources, categories, or notes have nulls."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                _add_requirement(
                    session, version.id, "req without metadata",
                    display_order=1, mandatory=None, clause=None,
                )
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import project_matrix_rows

        async def _project():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                return await project_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        row = rows[0]
        assert row.category is None
        assert row.clause is None
        assert row.source_page is None
        assert row.mandatory is None
        assert row.user_notes is None

    def test_exact_source_anchor_precedes_lower_approximate_page(self):
        """The matrix points to the page containing the literal quote."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                req = _add_requirement(session, version.id, "multi-page req", display_order=1)
                await session.flush()
                session.add_all([
                    RequirementSource(
                        requirement_id=req.id,
                        document_version_id=version.id,
                        page_number=5,
                        clause_number="5.2",
                        location_type="exact",
                        source_text="multi-page req",
                    ),
                    RequirementSource(
                        requirement_id=req.id,
                        document_version_id=version.id,
                        page_number=3,
                        clause_number="3.1",
                    ),
                    RequirementSource(
                        requirement_id=req.id,
                        document_version_id=version.id,
                        page_number=7,
                        clause_number="7.1",
                    ),
                ])
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import project_matrix_rows

        async def _project():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                return await project_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        assert rows[0].source_page == 5  # exact quote beats lower approximate page

    def test_multi_category_first_by_order(self):
        """When a requirement has multiple categories, the first by
        display_order is shown in the matrix."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                req = _add_requirement(
                    session, version.id, "multi-cat req", display_order=1
                )
                cat_a = Category(
                    project_id=project_id, name="Electrical", display_order=1
                )
                cat_b = Category(
                    project_id=project_id, name="Mechanical", display_order=0
                )
                session.add_all([cat_a, cat_b])
                await session.flush()
                await session.execute(
                    requirement_categories.insert().values(
                        requirement_id=req.id, category_id=cat_a.id
                    )
                )
                await session.execute(
                    requirement_categories.insert().values(
                        requirement_id=req.id, category_id=cat_b.id
                    )
                )
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import project_matrix_rows

        async def _project():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                return await project_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        # cat_b has display_order=0 which sorts before cat_a's display_order=1
        assert rows[0].category == "Mechanical"


class TestMatrixEndpoint:
    def test_matrix_endpoint_returns_rows(self):
        """GET /matrix returns projected rows."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                _add_requirement(
                    session, version.id, "Requirement A", display_order=1,
                    mandatory=True, clause="5.1",
                )
                _add_requirement(
                    session, version.id, "Requirement B", display_order=2,
                )
                await session.commit()

        asyncio.run(_setup())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/matrix",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["tender_requirement"] == "raw_Requirement A"
        assert data[0]["serial"] == 1
        assert data[0]["mandatory"] is True
        assert data[0]["clause"] == "5.1"
        assert data[1]["tender_requirement"] == "raw_Requirement B"
        assert data[1]["serial"] == 2
        # mandatory=None is excluded by exclude_none
        assert "mandatory" not in data[1]

    def test_matrix_excludes_superseded(self):
        """Superseded requirements are excluded from the matrix endpoint."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _setup():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                _add_requirement(session, version.id, "active", display_order=1)
                _add_requirement(
                    session, version.id, "superseded", display_order=2,
                    superseded=True,
                )
                await session.commit()

        asyncio.run(_setup())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/matrix",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tender_requirement"] == "raw_active"

    def test_matrix_tenant_isolation(self):
        """Cross-org access to matrix returns 404."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

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
                    Membership(
                        organization_id=other_org, user_id=other_user, role="owner"
                    )
                )
                await session.commit()
            return other_user, other_org

        other_user, other_org = asyncio.run(_other_org())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/matrix",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404
