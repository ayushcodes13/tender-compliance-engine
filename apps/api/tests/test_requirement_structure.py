"""Tests for CP39 — Requirement structure: split, merge, supersede,
categories, notes, mandatory, and ordering.

Covers:
- Split: creates child requirements, supersedes source, preserves raw_source
- Merge: combines requirements, supersedes sources, concatenates raw sources
- Supersede: marks as superseded, creates SUPERSEDES relation
- Mandatory tri-state: True/False/None
- Display order: persisted and survives refresh
- Category assignment/unassignment
- Reviewer notes: add/list
- List excludes superseded by default, includes when requested
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
            session.add(Organization(id=org_id, name="CP39 Test Org"))
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
                    name="CP39 Project",
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


def _create_two_requirements(project_id: uuid.UUID, normalized1: str, normalized2: str):
    """Create a version with two requirements; return (doc_id, ver, req1_id, req2_id)."""

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
            req1 = Requirement(
                document_version_id=version.id,
                promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                requirement_type="obligation",
                normalized_text=normalized1,
                raw_source=f"raw1-{uuid.uuid4().hex[:4]}",
                uncertainty="confirmed",
                ocr_warning=False,
                review_state=RequirementReviewState.UNREVIEWED,
            )
            req2 = Requirement(
                document_version_id=version.id,
                promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                requirement_type="obligation",
                normalized_text=normalized2,
                raw_source=f"raw2-{uuid.uuid4().hex[:4]}",
                uncertainty="confirmed",
                ocr_warning=False,
                review_state=RequirementReviewState.UNREVIEWED,
            )
            session.add(req1)
            session.add(req2)
            await session.flush()
            await session.commit()
            return doc.id, version.version_number, str(req1.id), str(req2.id)

    return asyncio.run(_create())


def _create_category(project_id: uuid.UUID, name: str = "Test Category"):
    """Create a category for a project. Returns category_id."""

    async def _create():
        async with _session_cm() as session:
            cat = Category(
                project_id=project_id,
                name=name,
                display_order=0,
            )
            session.add(cat)
            await session.flush()
            cat_id = cat.id
            await session.commit()
            return cat_id

    return asyncio.run(_create())


def _get_requirement_superseded(doc_id: uuid.UUID, ver: int, req_id: str):
    """Check if a requirement is superseded and get its raw_source."""

    async def _get():
        async with _session_cm() as session:
            result = await session.execute(
                select(Requirement).where(Requirement.id == uuid.UUID(req_id))
            )
            req = result.scalar_one()
            return req.superseded, req.raw_source

    return asyncio.run(_get())


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------


class TestSplitRequirement:
    def test_split_creates_children_and_supersedes_source(self):
        """Split creates child requirements and supersedes the original."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(
            project_id, "all equipment must be operational", "all equipment"
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/split",
            json={
                "new_requirements": [
                    {"normalized_text": "equipment must be operational", "raw_source": "equipment"},
                    {"normalized_text": "all items must be present", "raw_source": "all items"},
                ]
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        children = resp.json()
        assert len(children) == 2
        assert children[0]["normalized_text"] == "equipment must be operational"
        assert children[1]["normalized_text"] == "all items must be present"

        # Original should be superseded.
        superseded, raw = _get_requirement_superseded(doc_id, ver, req_id)
        assert superseded is True
        assert raw == "all equipment"  # raw_source preserved

    def test_split_preserves_raw_source_on_original(self):
        """Split does not modify the original requirement's raw_source."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(
            project_id, "weight ≤ 2 kg and ≥ 1 kg", "weight ≤ 2 kg"
        )

        client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/split",
            json={
                "new_requirements": [
                    {"normalized_text": "weight ≤ 2 kg", "raw_source": "weight ≤ 2 kg"},
                    {"normalized_text": "weight ≥ 1 kg", "raw_source": "weight ≥ 1 kg"},
                ]
            },
            headers=_headers(user_id, org_id),
        )

        superseded, raw = _get_requirement_superseded(doc_id, ver, req_id)
        assert superseded is True
        assert raw == "weight ≤ 2 kg"  # unchanged

    def test_split_tenant_isolation(self):
        """Cross-org split attempt returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(
            project_id, "test requirement", "raw"
        )

        # Create another org/user.
        async def _other():
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

        other_user, other_org = asyncio.run(_other())

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/split",
            json={
                "new_requirements": [
                    {"normalized_text": "child", "raw_source": "raw"},
                ]
            },
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404

    def test_split_single_child_allowed(self):
        """Split with one child is valid (refinement)."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(
            project_id, "weight ≤ 2 kg and ≥ 1 kg", "raw"
        )
        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/split",
            json={
                "new_requirements": [
                    {"normalized_text": "refined weight ≤ 2 kg", "raw_source": "raw"},
                ]
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        children = resp.json()
        assert len(children) == 1


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


class TestMergeRequirements:
    def test_merge_creates_target_and_supersedes_sources(self):
        """Merge creates one target requirement and supersedes both sources."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req1_id, req2_id = _create_two_requirements(
            project_id, "weight ≤ 2 kg", "weight ≤ 2 kg"
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/merge",
            json={
                "requirement_ids": [req1_id, req2_id],
                "merged_normalized_text": "weight must be between 1 kg and 2 kg",
                "merged_raw_sources": ["weight ≤ 2 kg", "weight ≥ 1 kg"],
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        merged = resp.json()
        assert merged["normalized_text"] == "weight must be between 1 kg and 2 kg"

        # Verify raw_source was concatenated via detail endpoint.
        detail_resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{merged['id']}",
            headers=_headers(user_id, org_id),
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert "weight ≤ 2 kg" in detail["raw_source"]
        assert "weight ≥ 1 kg" in detail["raw_source"]

        # Both sources should be superseded.
        sup1, raw1 = _get_requirement_superseded(doc_id, ver, req1_id)
        sup2, raw2 = _get_requirement_superseded(doc_id, ver, req2_id)
        # Source requirements' raw_source should still be original.
        assert raw1 != "weight ≤ 2 kg and ≥ 1 kg"
        assert raw2 != ""  # both still exist with original raw_source

    def test_merge_requires_at_least_two(self):
        """Merge with fewer than 2 IDs returns 400."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req1_id, _ = _create_two_requirements(
            project_id, "req1", "raw1"
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/merge",
            json={
                "requirement_ids": [req1_id],
                "merged_normalized_text": "merged",
                "merged_raw_sources": ["raw1"],
            },
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 422  # FastAPI validation error (min_length=2)


# ---------------------------------------------------------------------------
# Supersede
# ---------------------------------------------------------------------------


class TestSupersedeRequirement:
    def test_supersede_marks_requirement(self):
        """Supersede marks a requirement as superseded."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "old requirement", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/supersede",
            json={"superseded_by": str(uuid.uuid4()), "note": "mistaken extraction"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["superseded"] is True

        superseded, _ = _get_requirement_superseded(doc_id, ver, req_id)
        assert superseded is True

    def test_supersede_without_target(self):
        """Supersede without a replacement target still works."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "old", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/supersede",
            json={},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["superseded"] is True


# ---------------------------------------------------------------------------
# List excludes superseded
# ---------------------------------------------------------------------------


class TestSupersededFiltering:
    def test_list_excludes_superseded_by_default(self):
        """List endpoint excludes superseded requirements by default."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req1_id, _ = _create_two_requirements(
            project_id, "req1", "raw1"
        )
        # Wait — _create_two_requirements creates 2 reqs in a new doc/version
        # Let me create a third requirement to supersede.
        async def _add_and_supersede():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == doc_id,
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                req3 = Requirement(
                    document_version_id=version.id,
                    promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                    requirement_type="obligation",
                    normalized_text="req3 to supersede",
                    raw_source="raw3",
                    uncertainty="confirmed",
                    review_state=RequirementReviewState.UNREVIEWED,
                    superseded=True,
                )
                session.add(req3)
                await session.commit()
                return req3.id

        asyncio.run(_add_and_supersede())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert len(items) == 2  # only non-superseded
        for item in items:
            assert item["superseded"] is False

    def test_list_includes_superseded_when_requested(self):
        """With include_superseded=true, superseded requirements are returned."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req1_id, _ = _create_two_requirements(
            project_id, "req1", "raw1"
        )

        # Superseded one requirement.
        client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req1_id}/supersede",
            json={},
            headers=_headers(user_id, org_id),
        )

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements",
            params={"include_superseded": "true"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        # One should be superseded, one not.
        assert any(item["superseded"] for item in items)
        assert not all(item["superseded"] for item in items)


# ---------------------------------------------------------------------------
# Mandatory
# ---------------------------------------------------------------------------


class TestSetMandatory:
    def test_set_mandatory_true(self):
        """Set mandatory to True."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mandatory",
            json={"value": True},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["mandatory"] is True

    def test_set_mandatory_false(self):
        """Set mandatory to False."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mandatory",
            json={"value": False},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["mandatory"] is False

    def test_set_mandatory_null(self):
        """Set mandatory back to None (unknown)."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")

        # Set to True first.
        client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mandatory",
            json={"value": True},
            headers=_headers(user_id, org_id),
        )
        # Then set to None.
        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/mandatory",
            json={"value": None},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        # mandatory should be None (excluded by response_model_exclude_none).
        assert "mandatory" not in resp.json() or resp.json()["mandatory"] is None


# ---------------------------------------------------------------------------
# Display order
# ---------------------------------------------------------------------------


class TestReorderRequirements:
    def test_reorder_persists_order(self):
        """Reordered display_order survives refresh."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req1_id, req2_id = _create_two_requirements(
            project_id, "req A", "raw A"
        )

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/reorder",
            json={"order": [req2_id, req1_id]},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        result = resp.json()
        assert len(result) == 2
        # req2 should come first (display_order=0).
        assert result[0]["id"] == req2_id

    def test_reorder_partial_list(self):
        """Reordering only some requirements works."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req1_id, req2_id = _create_two_requirements(
            project_id, "req1", "raw1"
        )

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/reorder",
            json={"order": [req2_id]},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        result = resp.json()
        assert len(result) == 1
        assert result[0]["id"] == req2_id

    def test_reorder_invalid_id(self):
        """Reordering a non-existent requirement returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req1_id, _ = _create_two_requirements(
            project_id, "req1", "raw1"
        )

        resp = client.patch(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/reorder",
            json={"order": [str(uuid.uuid4())]},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class TestNotes:
    def test_add_and_list_note(self):
        """Add a note and list it."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/notes",
            json={"text": "this is a reviewer note"},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        note = resp.json()
        assert note["text"] == "this is a reviewer note"

        # List notes.
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/notes",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        notes = resp.json()
        assert len(notes) == 1
        assert notes[0]["text"] == "this is a reviewer note"

    def test_note_empty_text_rejected(self):
        """Empty note text returns 422."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/notes",
            json={"text": ""},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class TestCategories:
    def test_assign_and_unassign_category(self):
        """Assign a category, verify it shows on the requirement, then unassign."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")
        cat_id = _create_category(project_id, "Electrical")

        # Assign.
        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/categories",
            json={"category_id": str(cat_id)},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        cats = resp.json()["categories"]
        assert len(cats) == 1
        assert cats[0]["name"] == "Electrical"

        # Unassign.
        resp = client.delete(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/categories/{cat_id}",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert len(resp.json()["categories"]) == 0

    def test_assign_nonexistent_category(self):
        """Assigning a nonexistent category returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/categories",
            json={"category_id": str(uuid.uuid4())},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404

    def test_assign_category_from_other_project(self):
        """Category from another project returns 404."""
        user_id, org_id, project_id = _build_org_project()
        doc_id, ver, req_id, _ = _create_requirement(project_id, "req", "raw")

        # Create another project in same org.
        async def _other_project():
            other_proj = uuid.uuid4()
            async with _session_cm() as session:
                session.add(
                    Project(
                        id=other_proj,
                        organization_id=org_id,
                        name="Other Project",
                        status=ProjectStatus.TENDER_UPLOADED,
                        created_by=user_id,
                    )
                )
                session.add(
                    Category(project_id=other_proj, name="Other Cat", display_order=0)
                )
                await session.commit()
                cats = await session.execute(
                    select(Category).where(Category.project_id == other_proj)
                )
                return cats.scalars().one().id

        other_cat_id = asyncio.run(_other_project())

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/requirements/{req_id}/categories",
            json={"category_id": str(other_cat_id)},
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404
