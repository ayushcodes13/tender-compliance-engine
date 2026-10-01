"""API-level tests for the document upload route (CP13).

Exercises the full HTTP request/response cycle: validation, malware
scanning, storage, DB persistence, project-status transition, and
audit logging.  Uses :class:`FakeStorageAdapter` and
:class:`FakeScanner` via FastAPI dependency overrides.
"""

import asyncio
import io
import uuid

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select

from tender_compliance_api.db.models import (
    Membership,
    Organization,
    Project,
    ProjectStatus,
    StoredObject,
    User,
)
from tender_compliance_api.main import app
from tender_compliance_api.routes.uploads import get_scanner, get_storage_adapter
from tender_compliance_api.scan.fake import (
    TEST_INFECTED_SIGNATURE,
    FakeScanner,
)
from tender_compliance_api.storage.fake import FakeStorageAdapter

# Override storage and scanner dependencies for all tests in this module.
app.dependency_overrides[get_storage_adapter] = lambda: FakeStorageAdapter()
app.dependency_overrides[get_scanner] = lambda: FakeScanner()

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _make_valid_pdf() -> bytes:
    """Create a minimal valid single-page PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_protected_pdf(password: str = "secret") -> bytes:
    """Create a password-protected PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _build_auth_headers(session_cm) -> tuple[dict[str, str], uuid.UUID]:
    """Set up org + user + membership + project; return (headers, proj_id)."""

    async def _setup() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="Upload Test Org"))
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
                    name="Upload Project",
                    status=ProjectStatus.DRAFT,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    user_id, org_id, project_id = asyncio.run(_setup())
    return _headers(user_id, org_id), project_id


# ---------------------------------------------------------------------------
# Valid uploads
# ---------------------------------------------------------------------------


class TestUploadValid:
    def test_valid_pdf_upload(self, session_cm) -> None:
        """A valid PDF is accepted, stored, and project transitions to
        TENDER_UPLOADED."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["filename"] == "tender.pdf"
        assert body["content_type"] == "application/pdf"
        assert body["content_length"] == len(pdf_data)
        assert "checksum_sha256" in body
        assert body["project_status"] == "tender_uploaded"

        # Verify StoredObject was persisted in the DB.
        async def _verify() -> None:
            async with session_cm() as session:
                objs = (
                    await session.execute(
                        select(StoredObject).where(
                            StoredObject.project_id == project_id
                        )
                    )
                ).scalars().all()
                assert len(objs) == 1
                assert objs[0].checksum_sha256 == body["checksum_sha256"]

        asyncio.run(_verify())


# ---------------------------------------------------------------------------
# Rejected uploads
# ---------------------------------------------------------------------------


class TestUploadRejected:
    def test_mime_mismatch_rejected(self, session_cm) -> None:
        """File named .pdf but content lacks the PDF magic bytes."""
        headers, project_id = _build_auth_headers(session_cm)

        response = client.post(
            f"/projects/{project_id}/upload",
            files={
                "file": ("tender.pdf", b"NOT A PDF FILE CONTENTS", "application/pdf")
            },
            headers=headers,
        )

        assert response.status_code == 422
        assert "rejected" in response.json()["detail"].lower()

    def test_wrong_extension_rejected(self, session_cm) -> None:
        """PDF file with a disallowed extension is rejected."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_valid_pdf()

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.txt", pdf_data, "text/plain")},
            headers=headers,
        )

        assert response.status_code == 422
        assert "extension" in response.json()["detail"].lower()

    def test_empty_file_rejected(self, session_cm) -> None:
        """Empty uploads are rejected before any processing."""
        headers, project_id = _build_auth_headers(session_cm)

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()

    def test_protected_pdf_rejected(self, session_cm) -> None:
        """Password-protected PDFs are rejected."""
        headers, project_id = _build_auth_headers(session_cm)
        pdf_data = _make_protected_pdf()

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("protected.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 422
        detail = response.json()["detail"].lower()
        assert "password" in detail or "protected" in detail

    def test_malware_detected(self, session_cm) -> None:
        """Files containing a malware signature are rejected."""
        headers, project_id = _build_auth_headers(session_cm)

        # Valid PDF with malware test signature appended.
        pdf_data = _make_valid_pdf() + TEST_INFECTED_SIGNATURE

        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=headers,
        )

        assert response.status_code == 422
        assert "malware" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


class TestUploadAuthorization:
    def test_cross_tenant_denied(self, session_cm) -> None:
        """A user from org B cannot upload to a project in org A."""
        headers_a, project_id = _build_auth_headers(session_cm)

        # User from a different org.
        other_user = uuid.uuid4()
        other_org = uuid.uuid4()

        async def _setup_other() -> None:
            async with session_cm() as session:
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
                        organization_id=other_org,
                        user_id=other_user,
                        role="owner",
                    )
                )
                await session.commit()

        asyncio.run(_setup_other())

        pdf_data = _make_valid_pdf()
        response = client.post(
            f"/projects/{project_id}/upload",
            files={"file": ("tender.pdf", pdf_data, "application/pdf")},
            headers=_headers(other_user, other_org),
        )

        assert response.status_code == 404
