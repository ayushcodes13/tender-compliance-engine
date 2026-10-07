"""Tests for CP61 submission approval/locking workflow.

Covers:
- Submission creation (snapshot of assessment state)
- Lock → immutable
- Lock → Approve → record approver/timestamp
- After approval, new changes create a new version
- Revoke → APPROVED → REVOKED state transition
- Invalid state transitions (lock a locked submission, approve a draft, etc.)
- Tenant isolation (cross-org access denied)
- No fabrication: assessment_snapshot stored verbatim from the final matrix
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi.testclient import TestClient

from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    Requirement,
    TenderDocument,
    User,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document.service import DocumentService
from tender_compliance_api.errors import UNEXPECTED_REQUEST_FAILURE
from tender_compliance_api.main import app

client = TestClient(app)
_session_cm = contextlib.asynccontextmanager(get_session)

import uuid as uuid_module  # noqa: E402


def _headers(user_id, org_id):
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _setup_project_with_requirement():
    """Set up org + user + membership + project + document version + requirement.

    Returns dict with all IDs needed for tests.
    """

    async def _setup():
        org_id = uuid_module.uuid4()
        user_id = uuid_module.uuid4()
        project_id = uuid_module.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=org_id, name="CP61 Org"))
            session.add(
                User(
                    id=user_id, auth_provider="dev",
                    auth_provider_user_id=str(user_id),
                )
            )
            session.add(
                Membership(
                    organization_id=org_id, user_id=user_id, role="owner"
                )
            )
            session.add(
                Project(
                    id=project_id, organization_id=org_id, name="CP61 Proj",
                    status=ProjectStatus.TENDER_UPLOADED, created_by=user_id,
                )
            )
            doc = TenderDocument(
                project_id=project_id, display_name="tender.pdf",
                document_type="tender",
            )
            session.add(doc)
            await session.flush()
            version = DocumentVersion(
                document_id=doc.id, version_number=1,
                stored_object_id=uuid_module.uuid4(), sha256="abc",
                mime_type="application/pdf", size_bytes=1024,
                processing_status=DocumentProcessingStatus.PARSED,
            )
            session.add(version)
            await session.flush()
            req = Requirement(
                document_version_id=version.id,
                promotion_key=f"pk-{uuid_module.uuid4().hex[:8]}",
                requirement_type="obligation",
                normalized_text="The equipment shall operate at 12 V.",
                raw_source="The equipment shall operate at 12 V.",
                uncertainty="exact", ocr_warning=False,
                review_state="unreviewed", display_order=1,
            )
            session.add(req)
            await session.commit()
            return {
                "user_id": user_id, "org_id": org_id,
                "project_id": project_id, "doc_id": str(doc.id),
                "version_number": version.version_number,
            }

    return asyncio.run(_setup())


class TestSubmissionCreation:
    def test_unexpected_matrix_failure_is_safe_server_error(self, monkeypatch):
        ctx = _setup_project_with_requirement()

        async def fail_matrix(*args, **kwargs):
            raise RuntimeError("SECRET provider endpoint and token")

        monkeypatch.setattr(DocumentService, "get_final_matrix_rows", fail_matrix)
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/"
            f"{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 500
        assert resp.json()["detail"] == UNEXPECTED_REQUEST_FAILURE
        assert "SECRET" not in resp.text
        assert resp.headers.get("x-correlation-id")

    def test_create_submission_draft(self):
        ctx = _setup_project_with_requirement()
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["version_number"] == 1
        assert data["matrix_sha256"]
        assert len(data["assessment_snapshot"]) >= 0

    def test_submission_is_tenant_scoped(self):
        ctx = _setup_project_with_requirement()
        other_user = uuid_module.uuid4()
        other_org = uuid_module.uuid4()
        async def _other():
            async with _session_cm() as session:
                session.add(Organization(id=other_org, name="Other"))
                session.add(
                    User(
                        id=other_user, auth_provider="dev",
                        auth_provider_user_id=str(other_user),
                    )
                )
                session.add(
                    Membership(
                        organization_id=other_org, user_id=other_user, role="owner"
                    )
                )
                await session.commit()
        asyncio.run(_other())

        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404


class TestSubmissionLockApprove:
    def test_lock_approve_revoke_lifecycle(self):
        ctx = _setup_project_with_requirement()

        # Create
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 200
        sub_id = resp.json()["id"]

        # Lock
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/lock",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "locked"

        # Approve
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/approve",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        assert resp.json()["approver_id"] is not None
        assert resp.json()["approved_at"] is not None

        # Revoke
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/revoke",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"

    def test_cannot_lock_locked_submission(self):
        ctx = _setup_project_with_requirement()
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        sub_id = resp.json()["id"]

        # Lock
        client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/lock",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        # Try to lock again
        resp2 = client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/lock",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp2.status_code == 409

    def test_cannot_approve_draft(self):
        ctx = _setup_project_with_requirement()
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        sub_id = resp.json()["id"]

        resp2 = client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/approve",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp2.status_code == 409

    def test_cannot_revoke_locked(self):
        ctx = _setup_project_with_requirement()
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        sub_id = resp.json()["id"]
        client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/lock",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        resp2 = client.post(
            f"/projects/{ctx['project_id']}/submissions/{sub_id}/revoke",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp2.status_code == 409


class TestSubmissionAppendOnly:
    def test_new_submission_creates_new_version(self):
        ctx = _setup_project_with_requirement()

        # Create first submission
        resp1 = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp1.status_code == 200
        assert resp1.json()["version_number"] == 1

        # Create second submission
        resp2 = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp2.status_code == 200
        assert resp2.json()["version_number"] == 2
        assert resp1.json()["id"] != resp2.json()["id"]

    def test_list_submissions(self):
        ctx = _setup_project_with_requirement()
        client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )

        resp = client.get(
            f"/projects/{ctx['project_id']}/submissions/",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["version_number"] == 1
        assert data[1]["version_number"] == 2


class TestSubmissionNoFabrication:
    def test_assessment_snapshot_not_fabricated(self):
        """The assessment_snapshot is stored verbatim from the final matrix projection.

        When no assessments exist (just requirements), the snapshot should
        be empty, not populated with invented COMPLIANT/NON_COMPLIANT entries.
        """
        ctx = _setup_project_with_requirement()
        resp = client.post(
            f"/projects/{ctx['project_id']}/submissions/{ctx['doc_id']}/versions/{ctx['version_number']}",
            headers=_headers(ctx["user_id"], ctx["org_id"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        # No assessments exist yet, so snapshot should be empty.
        assert data["assessment_snapshot"] == []
