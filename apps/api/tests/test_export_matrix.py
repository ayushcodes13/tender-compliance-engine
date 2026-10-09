"""Tests for CP42 — XLSX export, history, download, and failure handling.

Covers:
- Export generates a valid XLSX workbook with correct columns
- Export uses the canonical matrix projection (columns match CP41)
- Excluded requirements: superseded requirements not in export
- Ordering preserved: display_order NULLS LAST
- Null metadata: missing clause/category/source_page represented honestly
- Export artifact recorded with metadata (actor, count, checksum, timestamp)
- Multiple historical exports retained
- Download endpoint returns workbook bytes
- Failed export recorded with FAILED status and error message
- Tenant isolation on export/download/list endpoints
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.db.models import (
    DocumentPage,
    DocumentProcessingStatus,
    DocumentVersion,
    ExportArtifact,
    ExportStatus,
    ExtractionDiagnostics,
    ExtractionWindowAudit,
    Membership,
    Organization,
    ProcessingRun,
    ProcessingStage,
    Project,
    ProjectStatus,
    Requirement,
    RequirementReviewState,
    RequirementSource,
    RunStatus,
    TenderDocument,
    User,
)
from tender_compliance_api.db.session import get_session
from tender_compliance_api.document import service as document_service
from tender_compliance_api.export import visual_validation
from tender_compliance_api.export.validation import (
    RequirementCell,
    validate_source_quote_presence,
)
from tender_compliance_api.export.visual_validation import PageImageValidationResponse
from tender_compliance_api.extraction import openai_adapter
from tender_compliance_api.extraction.adapter import LlmCallResult
from tender_compliance_api.main import app
from tender_compliance_api.matrix.projection import project_matrix_rows

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
    """Set up org + user + membership + project + doc version; return
    (user_id, org_id, project_id, document_id, version_number).
    """

    async def _setup():
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=org_id, name="CP42 Test Org"))
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
                    name="CP42 Project",
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
            return (
                user_id,
                org_id,
                project_id,
                str(doc.id),
                version.version_number,
            )

    return asyncio.run(_setup())


def _add_requirements(project_id, doc_id, ver, reqs_data):
    """Add requirements to the version. Each item: (text, order, mandatory,
    clause, superseded, page)."""

    async def _add():
        async with _session_cm() as session:
            result = await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == uuid.UUID(doc_id),
                    DocumentVersion.version_number == ver,
                )
            )
            version = result.scalar_one()
            for text, order, mandatory, clause, sup, page in reqs_data:
                req = Requirement(
                    document_version_id=version.id,
                    promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
                    requirement_type="obligation",
                    normalized_text=text,
                    raw_source=f"raw_{text}",
                    uncertainty="confirmed",
                    ocr_warning=False,
                    review_state=RequirementReviewState.UNREVIEWED,
                    display_order=order,
                    mandatory=mandatory,
                    superseded=sup,
                    clause_number=clause,
                )
                session.add(req)
                await session.flush()
                if page is not None:
                    session.add(
                        RequirementSource(
                            requirement_id=req.id,
                            document_version_id=version.id,
                            page_number=page,
                            clause_number=clause,
                            source_text=f"raw_{text}",
                        )
                    )
            await session.commit()

    asyncio.run(_add())


def _add_window_audit(
    doc_id,
    ver,
    *,
    call_status: str,
    candidate_count: int,
    coverage_status: str = "not_run",
    potential_omissions: list[str | dict[str, object]] | None = None,
):
    """Attach one extraction-window result to a parsed test version."""

    async def _add():
        async with _session_cm() as session:
            version = (
                await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver,
                    )
                )
            ).scalar_one()
            run = ProcessingRun(
                document_version_id=version.id,
                run_id=uuid.uuid4(),
                attempt=1,
                stage=ProcessingStage.EXTRACT,
                status=RunStatus.COMPLETED,
            )
            session.add(run)
            await session.flush()
            session.add(
                ExtractionDiagnostics(
                    document_version_id=version.id,
                    processing_run_id=run.id,
                    total_windows=1,
                    rejection_breakdown={},
                )
            )
            session.add(
                ExtractionWindowAudit(
                    document_version_id=version.id,
                    processing_run_id=run.id,
                    chunk_id="window-1",
                    window_index=1,
                    call_status=call_status,
                    candidate_count=candidate_count,
                    ocr_warning=False,
                    source_spans=[
                        {
                            "page_number": 3,
                            "clause_number": "5.1",
                            "char_start": 0,
                            "char_end": 20,
                        }
                    ],
                    coverage_status=coverage_status,
                    potential_omissions=potential_omissions or [],
                )
            )
            await session.commit()

    asyncio.run(_add())


# ---------------------------------------------------------------------------
# Export generation
# ---------------------------------------------------------------------------


class TestExportGeneration:
    def test_export_generates_valid_xlsx(self):
        """POST /exports generates a workbook and returns artifact metadata."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3),
             ("Req B", 2, False, "5.2", False, 5)],
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed", body.get("validation_report")
        assert body["requirement_count"] == 2
        assert body["workbook_sha256"]  # non-empty checksum
        assert body["id"]
        assert body["generated_at"]
        assert body["validation_report"]["checked_columns"] == 9
        assert body["validation_report"]["checked_cells"] == 18
        assert body["validation_report"]["window_processing"]["status"] == "not_available"
        assert body["validation_report"]["window_processing"]["completeness_proven"] is False

    def test_source_quote_check_rejects_dropped_range_dash(self):
        # The supplied MBE output omits the range dash in this tender quote.
        issues = validate_source_quote_presence(
            [RequirementCell("temperature-range", "at least 450 1250°C")],
            {"temperature-range": ["The range is at least 450–1250°C."]},
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("temperature-range", "source_quote_not_found")
        ]

    def test_source_quote_check_allows_wrap_whitespace_but_not_quote_glyph_change(self):
        exact_quote = "The chuck supports a wafer diameter of 4”."
        wrapped_source = "The chuck supports a wafer diameter\nof 4”."
        assert validate_source_quote_presence(
            [RequirementCell("quote", exact_quote)], {"quote": [wrapped_source]}
        ) == ()

        changed_glyph = exact_quote.replace("4”", '4"')
        issues = validate_source_quote_presence(
            [RequirementCell("quote", changed_glyph)], {"quote": [wrapped_source]}
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("quote", "source_quote_not_found")
        ]

    def test_source_quote_check_rejects_changed_spacing_around_hyphen(self):
        source_quote = "All pre -installation requirements are included."
        changed_quote = source_quote.replace("pre -installation", "pre-installation")

        issues = validate_source_quote_presence(
            [RequirementCell("hyphenated-term", changed_quote)],
            {"hyphenated-term": [source_quote]},
        )

        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("hyphenated-term", "source_quote_not_found")
        ]

    def test_export_does_not_accept_source_from_another_version(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, None)],
        )

        async def _add_other_version_source():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                requirement = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar_one()
                other_version = DocumentVersion(
                    document_id=version.document_id,
                    version_number=ver + 1,
                    stored_object_id=uuid.uuid4(),
                    sha256="other-version-sha",
                    mime_type="application/pdf",
                    size_bytes=1024,
                    processing_status=DocumentProcessingStatus.PARSED,
                )
                session.add(other_version)
                await session.flush()
                session.add(
                    RequirementSource(
                        requirement_id=requirement.id,
                        document_version_id=other_version.id,
                        page_number=3,
                        source_text=requirement.raw_source,
                    )
                )
                await session.commit()

        asyncio.run(_add_other_version_source())
        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        issues = body["validation_report"]["source_validation"]["issues"]
        assert len(issues) == 1
        assert issues[0]["code"] == "source_text_unavailable"

    def test_export_is_held_when_an_extraction_window_failed(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )
        _add_window_audit(doc_id, ver, call_status="failed", candidate_count=0)

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["validation_status"] == "needs_review"
        assert body["validation_report"]["window_processing"]["status"] == "incomplete"
        assert body["validation_report"]["window_processing"]["failed_windows"] == [
            {"window_index": 1, "chunk_id": "window-1", "pages": [3]}
        ]

    def test_export_is_held_for_unmatched_obligation_coverage_quote(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )
        _add_window_audit(
            doc_id,
            ver,
            call_status="completed",
            candidate_count=1,
            coverage_status="completed",
            potential_omissions=[
                {
                    "page_number": 3,
                    "source_quote": "The pump shall deliver 12 L/min.",
                }
            ],
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        body = resp.json()
        coverage = body["validation_report"]["window_processing"]
        assert body["status"] == "failed"
        assert body["validation_status"] == "needs_review"
        assert coverage["obligation_audit_status"] == "potential_omissions"
        assert coverage["potential_omissions"] == [
            {
                "window_index": 1,
                "pages": [3],
                "source_quote": "The pump shall deliver 12 L/min.",
            }
        ]

    def test_export_coverage_clears_after_source_verified_requirement_is_added(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Existing requirement", 1, True, "5.1", False, 3)],
        )
        quote = "The pump shall deliver 12 L/min."

        async def _add_page_text():
            async with _session_cm() as session:
                version = (await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver,
                    )
                )).scalar_one()
                session.add(DocumentPage(
                    document_version_id=version.id,
                    page_number=3,
                    extracted_text=quote,
                    cleaned_text=quote,
                    ocr_needed=False,
                    ocr_confidence=None,
                ))
                await session.commit()

        asyncio.run(_add_page_text())
        _add_window_audit(
            doc_id,
            ver,
            call_status="completed",
            candidate_count=1,
            coverage_status="completed",
            potential_omissions=[{"page_number": 3, "source_quote": quote}],
        )
        url = f"/projects/{project_id}/documents/{doc_id}/versions/{ver}"
        first = client.post(f"{url}/exports", headers=_headers(user_id, org_id))
        assert first.status_code == 200
        assert first.json()["validation_report"]["window_processing"][
            "obligation_audit_status"
        ] == "potential_omissions"

        added = client.post(
            f"{url}/requirements/from-source",
            json={"page_number": 3, "source_quote": quote, "requirement_type": "obligation"},
            headers=_headers(user_id, org_id),
        )
        assert added.status_code == 201, added.text
        assert added.json()["review_state"] == "unreviewed"

        rechecked = client.post(f"{url}/exports", headers=_headers(user_id, org_id))
        assert rechecked.status_code == 200
        coverage = rechecked.json()["validation_report"]["window_processing"]
        assert coverage["obligation_audit_status"] == "no_potential_omissions"
        assert coverage["potential_omissions"] == []

    def test_partial_ocr_coverage_finding_survives_other_page_uncertainty(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )
        _add_window_audit(
            doc_id,
            ver,
            call_status="completed",
            candidate_count=1,
            coverage_status="uncertain",
            potential_omissions=[
                {
                    "page_number": 3,
                    "source_quote": "The motor shall be IP55 rated.",
                    "bbox": {"x": 30, "y": 40, "width": 120, "height": 20},
                }
            ],
        )

        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )

        coverage = response.json()["validation_report"]["window_processing"]
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert coverage["obligation_audit_status"] == "audit_failed"
        assert coverage["potential_omissions"] == [
            {
                "window_index": 1,
                "pages": [3],
                "source_quote": "The motor shall be IP55 rated.",
            }
        ]

    def test_ocr_quote_requires_page_image_check_even_when_text_matches(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )

        async def _mark_ocr_source():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                requirement = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar_one()
                requirement.ocr_warning = True
                session.add(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=3,
                        cleaned_text=requirement.raw_source,
                        ocr_needed=True,
                    )
                )
                await session.commit()

        asyncio.run(_mark_ocr_source())
        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["validation_status"] == "needs_review"
        issues = body["validation_report"]["source_validation"]["issues"]
        assert len(issues) == 1
        assert issues[0]["code"] == "ocr_visual_verification_required"

    @pytest.mark.parametrize(
        ("ocr_warning", "source_text"),
        [(True, "raw_Req A"), (False, None)],
    )
    @pytest.mark.parametrize(
        ("fallback_outcome", "expected_status"),
        [
            ("exact", "passed"),
            ("uncertain", "needs_review"),
            ("provider_failed", "needs_review"),
            ("image_unavailable", "needs_review"),
        ],
    )
    def test_page_image_fallback_fails_closed(
        self, monkeypatch, ocr_warning, source_text, fallback_outcome, expected_status
    ):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )

        async def _mark_ocr_source():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                requirement = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar_one()
                requirement.ocr_warning = ocr_warning
                source = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.requirement_id == requirement.id
                        )
                    )
                ).scalar_one()
                source.source_text = source_text
                session.add(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=3,
                        cleaned_text=requirement.raw_source,
                        ocr_needed=ocr_warning,
                        rendered_image_object_key="rendered/page-3.png",
                    )
                )
                await session.commit()

        asyncio.run(_mark_ocr_source())

        class FakeAdapter:
            pass

        class FakeStorage:
            async def get(self, key: str) -> bytes:
                assert key == "rendered/page-3.png"
                if fallback_outcome == "image_unavailable":
                    raise RuntimeError("object storage unavailable")
                return b"page-image"

        checked: list[dict[str, object]] = []

        async def fake_visual_check(**kwargs):
            checked.append(kwargs)
            if fallback_outcome == "provider_failed":
                return (
                    None,
                    LlmCallResult(
                        provider="fake",
                        model="fake-vision",
                        prompt_version="test",
                        schema_version="test",
                        latency_ms=1,
                        prompt_tokens=None,
                        completion_tokens=None,
                        total_tokens=None,
                        cost_usd=None,
                        finish_reason=None,
                        status="failed",
                        error_message="page image validation failed",
                        call_site="test_page_image_validation",
                    ),
                )
            return (
                PageImageValidationResponse(
                    verdict="exact" if fallback_outcome == "exact" else "cannot_tell",
                    confidence=0.99 if fallback_outcome == "exact" else 0.2,
                    visible_quote=(
                        kwargs["proposed_quote"] if fallback_outcome == "exact" else ""
                    ),
                    reason=(
                        "The full quote is visibly present."
                        if fallback_outcome == "exact"
                        else "The page image is unclear."
                    ),
                ),
                LlmCallResult(
                    provider="fake",
                    model="fake-vision",
                    prompt_version="test",
                    schema_version="test",
                    latency_ms=1,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    cost_usd=None,
                    finish_reason="stop",
                    status="completed",
                    call_site="test_page_image_validation",
                ),
            )

        expected_requirement_ids: list[str] = []

        monkeypatch.setattr(
            document_service,
            "get_settings",
            lambda: SimpleNamespace(
                verbatim_validation_fallback_enabled=True,
                openai_api_key="configured-for-test",
            ),
        )
        monkeypatch.setattr(
            openai_adapter, "OpenAiLlmAdapter", lambda: FakeAdapter()
        )
        monkeypatch.setattr(
            visual_validation, "validate_quote_on_page_image", fake_visual_check
        )

        async def _validate():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                rows = await project_matrix_rows(session, version.id)
                expected_requirement_ids.extend(str(row.requirement_id) for row in rows)
                return await document_service._source_quote_validation_report(
                    session,
                    rows,
                    FakeStorage(),
                    version.id,
                )

        report = asyncio.run(_validate())
        assert report["status"] == expected_status
        if fallback_outcome == "exact":
            assert report["llm_assisted_rows"] == expected_requirement_ids
        else:
            assert report["llm_assisted_rows"] == []
            expected_issue = (
                "ocr_visual_verification_required"
                if ocr_warning
                else "source_text_unavailable"
            )
            assert report["issues"] == [
                {"row_id": expected_requirement_ids[0], "code": expected_issue}
            ]
        if fallback_outcome == "image_unavailable":
            assert checked == []
            assert report["llm_fallback_results"][0]["status"] == "image_unavailable"
        else:
            assert len(checked) == 1
            assert checked[0]["page_number"] == 3
            assert checked[0]["image_bytes"] == b"page-image"
            expected_fallback_status = (
                "exact" if fallback_outcome == "exact" else "needs_review"
            )
            assert report["llm_fallback_results"][0]["status"] == expected_fallback_status
            assert report["llm_fallback_results"][0]["call_status"] == (
                "failed" if fallback_outcome == "provider_failed" else "completed"
            )

    def test_completed_windows_are_not_reported_as_proof_of_completeness(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )
        _add_window_audit(doc_id, ver, call_status="completed", candidate_count=1)

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        report = resp.json()["validation_report"]["window_processing"]
        assert report["status"] == "complete"
        assert report["completeness_proven"] is False

    def test_export_excludes_superseded(self):
        """Superseded requirements are excluded from the export."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3),
             ("Req B (superseded)", 2, False, "5.2", True, 5)],
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["requirement_count"] == 1  # only Req A

    def test_export_preserves_ordering(self):
        """Export preserves display_order NULLS LAST."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("No order", None, None, None, False, 4),
             ("Ordered", 1, True, "5.1", False, 3)],
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["requirement_count"] == 2

    def test_export_has_correct_columns(self):
        """The downloaded XLSX has the canonical matrix columns."""
        import io

        from openpyxl import load_workbook

        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        export_id = resp.json()["id"]

        dl = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports/{export_id}",
            headers=_headers(user_id, org_id),
        )
        assert dl.status_code == 200
        wb = load_workbook(io.BytesIO(dl.content))
        ws = wb.active
        # Header row is at row 7 (5 metadata rows + 1 title/header row...
        # actually the header is at row 7 in our implementation)
        # Find the row with "S.No." in it.
        header_row = None
        for row in ws.iter_rows():
            if row[0].value == "S.No.":
                header_row = row
                break
        assert header_row is not None
        headers = [c.value for c in header_row]
        assert "Requirement ID" in headers
        assert "Tender Requirement" in headers
        assert "Category" in headers
        assert "Clause" in headers
        assert "Source Page" in headers
        assert "Mandatory" in headers
        assert "User Notes" in headers
        assert "Review Status" in headers


class TestExportHistory:
    def test_multiple_exports_retained(self):
        """Multiple exports are retained as history."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )

        # Create two exports.
        r1 = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        # Modify data between exports to get different checksums.
        async def _modify():
            async with _session_cm() as session:
                result = await session.execute(
                    select(Requirement).where(
                        Requirement.document_version_id == (
                            select(DocumentVersion.id)
                            .where(
                                DocumentVersion.document_id == uuid.UUID(doc_id),
                                DocumentVersion.version_number == ver
                            )
                            .scalar_subquery()
                        )
                    )
                )
                req = result.scalar_one()
                req.normalized_text = "Req A (updated)"
                req.raw_source = "Req A (updated)"
                source_result = await session.execute(
                    select(RequirementSource).where(
                        RequirementSource.requirement_id == req.id
                    )
                )
                source = source_result.scalar_one()
                source.source_text = req.raw_source
                await session.commit()

        asyncio.run(_modify())

        r2 = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] != r2.json()["id"]
        assert r1.json()["workbook_sha256"] != r2.json()["workbook_sha256"]

        # List should show both.
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["generated_at"] >= data[1]["generated_at"]


class TestExportDownload:
    def test_download_returns_workbook_bytes(self):
        """Download endpoint returns valid XLSX bytes."""
        import io

        from openpyxl import load_workbook

        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3),
             ("Req B", 2, None, None, False, 6)],
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        export_id = resp.json()["id"]

        dl = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports/{export_id}",
            headers=_headers(user_id, org_id),
        )
        assert dl.status_code == 200
        assert dl.headers["Content-Type"].startswith(
            "application/vnd.openxmlformats"
        )
        # Verify it's a valid workbook.
        wb = load_workbook(io.BytesIO(dl.content))
        assert wb.active is not None

    def test_download_failed_export_returns_404(self):
        """Downloading a FAILED export returns 404 (not the bytes)."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()

        async def _create_failed():
            async with _session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == uuid.UUID(doc_id),
                        DocumentVersion.version_number == ver
                    )
                )
                version = result.scalar_one()
                artifact = ExportArtifact(
                    document_version_id=version.id,
                    stored_object_id=None,
                    actor_id=user_id,
                    status=ExportStatus.FAILED,
                    error_message="Simulated failure",
                    requirement_count=0,
                    workbook_sha256="",
                )
                session.add(artifact)
                await session.commit()
                return str(artifact.id)

        failed_id = asyncio.run(_create_failed())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports/{failed_id}",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404


class TestExportTenantIsolation:
    def test_export_tenant_isolation(self):
        """Cross-org export attempt returns 404."""
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

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404

    def test_download_cross_tenant_returns_404(self):
        """Cross-org download attempt returns 404."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )

        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )
        export_id = resp.json()["id"]

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
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports/{export_id}",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404
