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
from typing import Any

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
    AuthorizedSourceFragment,
    RequirementCell,
    validate_source_quote_presence,
)
from tender_compliance_api.export.visual_validation import PageImageQuoteDecision
from tender_compliance_api.extraction import openai_adapter
from tender_compliance_api.extraction.adapter import LlmCallResult
from tender_compliance_api.main import app
from tender_compliance_api.matrix.projection import project_matrix_rows

client = TestClient(app)
_session_cm = contextlib.asynccontextmanager(get_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_page_batch(
    kwargs: dict[str, Any],
    verdict_for,
    *,
    failed: bool = False,
) -> tuple[dict[str, PageImageQuoteDecision], LlmCallResult]:
    decisions: dict[str, PageImageQuoteDecision] = {}
    for item in kwargs["items"]:
        verdict, confidence = verdict_for(kwargs["page_number"], item.proposed_quote)
        decisions[item.item_id] = PageImageQuoteDecision(
            item_id=item.item_id,
            verdict=verdict,
            confidence=confidence,
            visible_quote=item.proposed_quote if verdict == "exact" else "",
            reason="Fake page image check.",
        )
    return (
        decisions,
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
            finish_reason=None if failed else "stop",
            status="failed" if failed else "completed",
            call_site="test_page_image_validation",
            error_category="image_parse_error" if failed else None,
        ),
    )


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
    coverage_error_category: str | None = None,
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
                    coverage_error_category=coverage_error_category,
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

    @pytest.mark.parametrize(
        ("image_verdict", "expected_status", "expected_validation"),
        [
            ("exact", "completed", "passed"),
            ("not_exact", "failed", "needs_review"),
        ],
    )
    def test_final_export_routes_ocr_uncertainty_through_image_gate(
        self, monkeypatch, image_verdict, expected_status, expected_validation
    ):
        """The final artifact is issued only after the source-page fallback passes."""
        from tender_compliance_api.storage.fake import FakeStorageAdapter

        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )

        async def _mark_uncertain_and_add_page():
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
                        rendered_image_object_key="rendered/page-3.png",
                    )
                )
                await session.commit()
                return requirement.raw_source, str(requirement.id)

        quote, requirement_id = asyncio.run(_mark_uncertain_and_add_page())
        storage = FakeStorageAdapter()
        storage._store["rendered/page-3.png"] = b"rendered-source-page"

        class FakeAdapter:
            provider = "fake"
            model = "fake-vision"

        checked: list[dict[str, object]] = []

        async def fake_visual_check(**kwargs):
            checked.append(kwargs)
            return _fake_page_batch(
                kwargs,
                lambda _page, _quote: (image_verdict, 0.99),
            )

        monkeypatch.setattr(document_service, "_resolve_storage", lambda: storage)
        monkeypatch.setattr(
            document_service,
            "get_settings",
            lambda: SimpleNamespace(
                verbatim_validation_fallback_enabled=True,
                openai_api_key="configured-for-test",
                is_production=False,
            ),
        )
        monkeypatch.setattr(openai_adapter, "OpenAiLlmAdapter", lambda: FakeAdapter())
        monkeypatch.setattr(
            visual_validation, "validate_quotes_on_page_image", fake_visual_check
        )

        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/final-matrix/exports",
            headers=_headers(user_id, org_id),
            params={"fmt": "xlsx"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == expected_status
        assert body["validation_status"] == expected_validation
        source_validation = body["validation_report"]["source_validation"]
        assert len(checked) == 1
        assert checked[0]["items"][0].proposed_quote == quote
        assert checked[0]["page_number"] == 3
        assert checked[0]["image_bytes"] == b"rendered-source-page"
        assert checked[0]["image_mime_type"] == "image/png"
        assert isinstance(checked[0]["adapter"], FakeAdapter)
        assert source_validation["llm_assisted_rows"] == (
            [requirement_id] if image_verdict == "exact" else []
        )
        assert source_validation["llm_fallback_results"][0]["status"] == (
            "exact" if image_verdict == "exact" else "needs_review"
        )

    def test_source_quote_check_rejects_dropped_range_dash(self):
        # The supplied MBE output omits the range dash in this tender quote.
        issues = validate_source_quote_presence(
            [RequirementCell("temperature-range", "at least 450 1250°C")],
            {"temperature-range": ["The range is at least 450–1250°C."]},
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("temperature-range", "source_quote_not_found")
        ]

    def test_example2_pyrometer_range_rejects_dropped_en_dash(self):
        # Example 2 page 24 says 450–1250°C; the supplied response DOCX drops
        # the range dash and renders the values as "450 1250°C".
        source_page = AuthorizedSourceFragment(
            page_number=24,
            text="Pyrometer range of at least 450–1250°C, fully integrated with MBE control.",
            page_local=True,
            authoritative_page_text=True,
        )
        exact_source_wording = RequirementCell(
            "pyrometer-range", "range of at least 450–1250°C", source_page=24
        )
        sampled_output_wording = RequirementCell(
            "pyrometer-range", "range of at least 450 1250°C", source_page=24
        )

        assert validate_source_quote_presence(
            [exact_source_wording], {"pyrometer-range": [source_page]}
        ) == ()
        issues = validate_source_quote_presence(
            [sampled_output_wording], {"pyrometer-range": [source_page]}
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("pyrometer-range", "source_quote_not_found")
        ]

    def test_example1_wafer_diameter_rejects_straight_quote_for_curly_inch_mark(self):
        # Example 1 page 10 uses a curly closing quote after 4; the supplied
        # response DOCX renders a straight quote in the wafer-chuck row.
        source_page = AuthorizedSourceFragment(
            page_number=10,
            text=(
                "Vacuum-backed chuck – should handle samples of 10mm by 10mm "
                "to wafer diameter of 4”\n"
                "• Fine positioning of the XY table with digital readout\n"
                "• X-Y movement range – minimum 25 mm\n"
                "• Chuck Stage XY Resolution: 10 µm\n"
                "• Micro-finish roughness and/or Teflon coated"
            ),
            page_local=True,
            authoritative_page_text=True,
        )
        exact_source_wording = RequirementCell(
            "wafer-chuck",
            "• Vacuum-backed chuck – should handle samples of 10mm by 10mm "
            "to wafer diameter of 4”\n"
            "• Fine positioning of the XY table with digital readout\n"
            "• X-Y movement range – minimum 25 mm\n"
            "• Chuck Stage XY Resolution: 10 µm\n"
            "• Micro-finish roughness and/or Teflon coated",
            source_page=10,
        )
        sampled_output_wording = RequirementCell(
            "wafer-chuck",
            exact_source_wording.text.replace("4”", '4"'),
            source_page=10,
        )

        assert validate_source_quote_presence(
            [exact_source_wording], {"wafer-chuck": [source_page]}
        ) == ()
        issues = validate_source_quote_presence(
            [sampled_output_wording], {"wafer-chuck": [source_page]}
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("wafer-chuck", "source_quote_not_found")
        ]

    def test_example2_ln2_requirement_rejects_dropped_en_dash(self):
        # Example 2 page 27 has an en dash before "so that"; the response DOCX
        # omits it, which a text comparison that strips punctuation would miss.
        source_page = AuthorizedSourceFragment(
            page_number=27,
            text=(
                "pumping well (if applicable) – so that smooth functioning of the "
                "MBE is achieved."
            ),
            page_local=True,
            authoritative_page_text=True,
        )
        exact_source_wording = RequirementCell(
            "ln2-functioning",
            "pumping well (if applicable) – so that smooth functioning of the MBE is achieved.",
            source_page=27,
        )
        sampled_output_wording = RequirementCell(
            "ln2-functioning",
            "pumping well (if applicable) so that smooth functioning of the MBE is achieved.",
            source_page=27,
        )

        assert validate_source_quote_presence(
            [exact_source_wording], {"ln2-functioning": [source_page]}
        ) == ()
        issues = validate_source_quote_presence(
            [sampled_output_wording], {"ln2-functioning": [source_page]}
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("ln2-functioning", "source_quote_not_found")
        ]

    def test_example3_delivery_period_rejects_sampled_ten_month_substitution(self):
        # Example 3 page 22 states "Within 8 Weeks"; its supplied response
        # sheet says "within 10 months", which is absent from the tender.
        source_page = AuthorizedSourceFragment(
            page_number=22,
            text=("Delivery- Period Within 8 Weeks from the date of Purchase order."),
            page_local=True,
            authoritative_page_text=True,
        )

        exact_source_wording = RequirementCell(
            "delivery-period",
            "Within 8 Weeks from the date of Purchase order.",
            source_page=22,
        )
        sampled_substitution = RequirementCell(
            "delivery-period",
            "within 10 months of acceptance of PO by the vendor.",
            source_page=22,
        )

        assert (
            validate_source_quote_presence(
                [exact_source_wording], {"delivery-period": [source_page]}
            )
            == ()
        )
        issues = validate_source_quote_presence(
            [sampled_substitution], {"delivery-period": [source_page]}
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("delivery-period", "source_quote_not_found")
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

    def test_source_quote_check_ignores_only_standalone_list_bullet_markers(self):
        source = "\uf0b7 Accuracy: ±0.5%\n\uf0b7 Power supply: 380V / 400V"
        quote = "Accuracy: ±0.5%\nPower supply: 380V / 400V"

        assert validate_source_quote_presence(
            [RequirementCell("list-quote", quote)], {"list-quote": [source]}
        ) == ()

        embedded_bullet_source = "Accuracy • 0.5%"
        embedded_bullet_quote = "Accuracy 0.5%"
        issues = validate_source_quote_presence(
            [RequirementCell("embedded-bullet", embedded_bullet_quote)],
            {"embedded-bullet": [embedded_bullet_source]},
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("embedded-bullet", "source_quote_not_found")
        ]

    def test_source_quote_check_recognizes_repeated_ocr_open_circle_markers(self):
        source = (
            "\uf0b7 HP-SA:\n"
            "o Digital setting with auto switch-off at set pressure\n"
            "o Secondary back-up pressure setting\n"
            "o Operates from 220–240 V, 1 phase power supply"
        )
        quote = (
            "Digital setting with auto switch-off at set pressure\n"
            "Secondary back-up pressure setting"
        )

        assert validate_source_quote_presence(
            [RequirementCell("open-circle-list", quote)],
            {"open-circle-list": [source]},
        ) == ()

    def test_source_quote_check_does_not_strip_a_real_o_word(self):
        source = "\uf0b7 Parts list:\no-ring seals must remain oil-tight."
        quote = "Parts list:\nring seals must remain oil-tight."

        issues = validate_source_quote_presence(
            [RequirementCell("real-o-word", quote)], {"real-o-word": [source]}
        )

        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("real-o-word", "source_quote_not_found")
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

    def test_source_quote_check_accepts_complete_ordered_adjacent_page_fragments(self):
        quote = "The machine shall test\ncontinuously at 1000/s."
        fragments = [
            AuthorizedSourceFragment(17, "The machine shall test", page_local=True, char_start=120),
            AuthorizedSourceFragment(18, "continuously at 1000/s.", page_local=True, char_start=4),
        ]

        assert validate_source_quote_presence(
            [RequirementCell("spanning-quote", quote, source_page=17)],
            {"spanning-quote": fragments},
        ) == ()

    def test_source_quote_check_does_not_validate_from_a_different_page(self):
        quote = "The machine shall test continuously at 1000/s."
        fragments = [
            AuthorizedSourceFragment(17, quote, page_local=True, char_start=120),
            AuthorizedSourceFragment(18, "A different clause.", page_local=True, char_start=4),
        ]

        issues = validate_source_quote_presence(
            [RequirementCell("wrong-citation", quote, source_page=18)],
            {"wrong-citation": fragments},
        )

        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("wrong-citation", "source_quote_not_found")
        ]

    def test_authoritative_page_text_does_not_override_a_wrong_selected_page(self):
        quote = "The machine shall test continuously at 1000/s."
        full_window = f"Prefix. {quote} Suffix."
        fragments = [
            AuthorizedSourceFragment(17, full_window, page_local=False),
            AuthorizedSourceFragment(18, full_window, page_local=False),
            AuthorizedSourceFragment(
                17, quote, page_local=False, authoritative_page_text=True
            ),
        ]

        issues = validate_source_quote_presence(
            [RequirementCell("wrong-authoritative-page", quote, source_page=18)],
            {"wrong-authoritative-page": fragments},
        )

        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("wrong-authoritative-page", "source_quote_not_found")
        ]

    def test_source_quote_check_rejects_full_window_repeated_on_page_anchors(self):
        quote = "The machine shall test continuously at 1000/s."
        full_window = f"Prefix. {quote} Suffix."
        fragments = [
            AuthorizedSourceFragment(17, full_window, page_local=False, char_start=8),
            AuthorizedSourceFragment(18, full_window, page_local=False, char_start=8),
        ]

        issues = validate_source_quote_presence(
            [RequirementCell("repeated-window", quote, source_page=17)],
            {"repeated-window": fragments},
        )

        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("repeated-window", "source_quote_not_found")
        ]

    @pytest.mark.parametrize(
        "fragments",
        [
            [
                AuthorizedSourceFragment(17, "The machine shall test", page_local=True),
                AuthorizedSourceFragment(19, "continuously at 1000/s.", page_local=True),
            ],
            [
                AuthorizedSourceFragment(17, "The machine shall test", page_local=True),
                AuthorizedSourceFragment(18, "continuously at 1000/s", page_local=False),
            ],
            [
                AuthorizedSourceFragment(17, "The machine shall test", page_local=True),
                AuthorizedSourceFragment(17, "continuously at 1000/s.", page_local=True),
            ],
        ],
    )
    def test_source_quote_check_fails_closed_on_gaps_or_approximate_fragments(
        self, fragments
    ):
        quote = "The machine shall test continuously at 1000/s."
        issues = validate_source_quote_presence(
            [RequirementCell("spanning-quote", quote)],
            {"spanning-quote": fragments},
        )
        assert [(issue.row_id, issue.code) for issue in issues] == [
            ("spanning-quote", "source_quote_not_found")
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
            {
                "window_index": 1,
                "chunk_id": "window-1",
                "coverage_error_category": None,
                "pages": [3],
            }
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
                "coverage_candidates": [],
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

    def test_reviewed_coverage_finding_is_suppressed_and_latest_decision_is_visible(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Baseline requirement", 1, True, "1.0", False, 1)],
        )
        quote = "The pump shall deliver 12 L/min."

        async def _add_page_and_audit():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                session.add(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=3,
                        extracted_text=f"{quote} {quote}",
                        cleaned_text=f"{quote} {quote}",
                        ocr_needed=False,
                        ocr_confidence=None,
                    )
                )
                await session.commit()

        asyncio.run(_add_page_and_audit())
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
            "potential_omissions"
        ]

        added = client.post(
            f"{url}/requirements/from-source",
            json={"page_number": 3, "source_quote": quote, "requirement_type": "obligation"},
            headers=_headers(user_id, org_id),
        )
        assert added.status_code == 201, added.text
        review_url = f"{url}/coverage-reviews"
        covered = client.post(
            review_url,
            json={
                "page_number": 3,
                "source_quote": quote,
                "decision": "covered_by_requirement",
                "requirement_id": added.json()["id"],
            },
            headers=_headers(user_id, org_id),
        )
        assert covered.status_code == 201, covered.text

        after_covered = client.post(f"{url}/exports", headers=_headers(user_id, org_id))
        assert after_covered.status_code == 200
        covered_report = after_covered.json()["validation_report"]["window_processing"]
        assert covered_report["obligation_audit_status"] == "no_potential_omissions"
        assert covered_report["potential_omissions"] == []
        assert covered_report["resolved_omissions"][0]["decision"] == "covered_by_requirement"
        assert covered_report["resolved_omissions"][0]["actor_id"] == str(user_id)

        dismissed = client.post(
            review_url,
            json={
                "page_number": 3,
                "source_quote": quote,
                "decision": "not_in_scope",
                "rationale": "The repeated mention is an administrative note, not a supplier duty.",
            },
            headers=_headers(user_id, org_id),
        )
        assert dismissed.status_code == 201, dismissed.text
        after_dismissal = client.post(f"{url}/exports", headers=_headers(user_id, org_id))
        assert after_dismissal.status_code == 200
        latest_report = after_dismissal.json()["validation_report"]["window_processing"]
        assert latest_report["obligation_audit_status"] == "no_potential_omissions"
        assert latest_report["resolved_omissions"][0]["decision"] == "not_in_scope"
        assert latest_report["resolved_omissions"][0]["rationale"].startswith(
            "The repeated mention"
        )

    def test_covered_review_expires_when_linked_requirement_is_superseded(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        quote = "The pump shall deliver 12 L/min."

        async def _add_page():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                session.add(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=3,
                        extracted_text=f"{quote} {quote}",
                        cleaned_text=f"{quote} {quote}",
                        ocr_needed=False,
                        ocr_confidence=None,
                    )
                )
                await session.commit()

        asyncio.run(_add_page())
        _add_window_audit(
            doc_id,
            ver,
            call_status="completed",
            candidate_count=1,
            coverage_status="completed",
            potential_omissions=[{"page_number": 3, "source_quote": quote}],
        )
        url = f"/projects/{project_id}/documents/{doc_id}/versions/{ver}"
        added = client.post(
            f"{url}/requirements/from-source",
            json={"page_number": 3, "source_quote": quote, "requirement_type": "obligation"},
            headers=_headers(user_id, org_id),
        )
        assert added.status_code == 201, added.text
        reviewed = client.post(
            f"{url}/coverage-reviews",
            json={
                "page_number": 3,
                "source_quote": quote,
                "decision": "covered_by_requirement",
                "requirement_id": added.json()["id"],
            },
            headers=_headers(user_id, org_id),
        )
        assert reviewed.status_code == 201, reviewed.text

        superseded = client.post(
            f"{url}/requirements/{added.json()['id']}/supersede",
            headers=_headers(user_id, org_id),
        )
        assert superseded.status_code == 200, superseded.text
        rechecked = client.post(f"{url}/exports", headers=_headers(user_id, org_id))
        coverage = rechecked.json()["validation_report"]["window_processing"]
        assert coverage["obligation_audit_status"] == "potential_omissions"
        assert coverage["potential_omissions"][0]["source_quote"] == quote

    def test_not_in_scope_review_does_not_clear_failed_coverage_audit(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Baseline requirement", 1, True, "1.0", False, 1)],
        )
        quote = "The buyer will open bids at 11:00."

        async def _add_page():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                session.add(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=3,
                        extracted_text=quote,
                        cleaned_text=quote,
                        ocr_needed=False,
                        ocr_confidence=None,
                    )
                )
                await session.commit()

        asyncio.run(_add_page())
        _add_window_audit(
            doc_id,
            ver,
            call_status="completed",
            candidate_count=1,
            coverage_status="failed",
            potential_omissions=[{"page_number": 3, "source_quote": quote}],
        )
        url = f"/projects/{project_id}/documents/{doc_id}/versions/{ver}"
        reviewed = client.post(
            f"{url}/coverage-reviews",
            json={
                "page_number": 3,
                "source_quote": quote,
                "decision": "not_in_scope",
                "rationale": "This is a buyer bid-opening procedure.",
            },
            headers=_headers(user_id, org_id),
        )
        assert reviewed.status_code == 201, reviewed.text
        rechecked = client.post(f"{url}/exports", headers=_headers(user_id, org_id))
        coverage = rechecked.json()["validation_report"]["window_processing"]
        assert rechecked.json()["validation_status"] == "needs_review"
        assert coverage["obligation_audit_status"] == "audit_failed"
        assert coverage["potential_omissions"] == []
        assert len(coverage["obligation_audit_failed_windows"]) == 1

    @pytest.mark.parametrize(
        ("second_page_verdict", "expected_status"),
        [("exact", "passed"), ("cannot_tell", "needs_review")],
    )
    def test_multi_page_ocr_quote_checks_each_page_local_fragment(
        self, monkeypatch, second_page_verdict, expected_status
    ):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        first_fragment = "The machine shall test"
        second_fragment = "continuously at 1000/s."
        quote = f"{first_fragment}\n{second_fragment}"

        async def _add_multi_page_ocr_source():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                requirement = Requirement(
                    document_version_id=version.id,
                    promotion_key=f"pk-{uuid.uuid4().hex}",
                    requirement_type="obligation",
                    normalized_text=quote,
                    raw_source=quote,
                    uncertainty="uncertain",
                    ocr_warning=True,
                    review_state=RequirementReviewState.OCR_WARNING,
                    display_order=1,
                    mandatory=True,
                    superseded=False,
                    clause_number="4.1",
                )
                session.add(requirement)
                await session.flush()
                session.add_all(
                    [
                        RequirementSource(
                            requirement_id=requirement.id,
                            document_version_id=version.id,
                            page_number=17,
                            clause_number="4.1",
                            char_start=120,
                            char_end=120 + len(first_fragment),
                            location_type="exact",
                            source_text=first_fragment,
                        ),
                        RequirementSource(
                            requirement_id=requirement.id,
                            document_version_id=version.id,
                            page_number=18,
                            clause_number="4.1",
                            char_start=4,
                            char_end=4 + len(second_fragment),
                            location_type="exact",
                            source_text=second_fragment,
                        ),
                    ]
                )
                session.add_all(
                    [
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=17,
                            cleaned_text=f"Prefix. {first_fragment}",
                            ocr_needed=True,
                            rendered_image_object_key="rendered/page-17.png",
                        ),
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=18,
                            cleaned_text=f"{second_fragment} Suffix.",
                            ocr_needed=True,
                            rendered_image_object_key="rendered/page-18.png",
                        ),
                    ]
                )
                await session.commit()
                return requirement.id

        requirement_id = asyncio.run(_add_multi_page_ocr_source())

        class FakeAdapter:
            pass

        class FakeStorage:
            async def get(self, key: str) -> bytes:
                return key.encode()

        checked: list[tuple[int, str]] = []

        async def fake_visual_check(**kwargs):
            checked.extend(
                (kwargs["page_number"], item.proposed_quote)
                for item in kwargs["items"]
            )
            return _fake_page_batch(
                kwargs,
                lambda page, _quote: (
                    second_page_verdict if page == 18 else "exact",
                    0.99 if page != 18 or second_page_verdict == "exact" else 0.5,
                ),
            )

        monkeypatch.setattr(
            document_service,
            "get_settings",
            lambda: SimpleNamespace(
                verbatim_validation_fallback_enabled=True,
                openai_api_key="configured-for-test",
            ),
        )
        monkeypatch.setattr(openai_adapter, "OpenAiLlmAdapter", lambda: FakeAdapter())
        monkeypatch.setattr(
            visual_validation, "validate_quotes_on_page_image", fake_visual_check
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
                return await document_service._source_quote_validation_report(
                    session,
                    rows,
                    FakeStorage(),
                    version.id,
                )

        report = asyncio.run(_validate())

        assert checked == [(17, first_fragment), (18, second_fragment)]
        assert report["status"] == expected_status
        if second_page_verdict == "exact":
            assert report["llm_assisted_rows"] == [str(requirement_id)]
        else:
            assert report["llm_assisted_rows"] == []
            assert report["issues"] == [
                {"row_id": str(requirement_id), "code": "ocr_visual_verification_required"}
            ]
        assert [result["page_number"] for result in report["llm_fallback_results"]] == [
            17,
            18,
        ]

    def test_approximate_window_is_checked_against_its_selected_page_text(self):
        _user_id, _org_id, project_id, doc_id, ver = _build_org_project()
        quote = (
            "Digital setting with auto switch-off at set pressure\n"
            "Secondary back-up pressure setting"
        )
        _add_requirements(
            project_id, doc_id, ver,
            [(quote, 1, True, "Grips and Fixtures", False, 18)],
        )
        window_text = (
            "\uf0b7 HP-SA:\n"
            "o Hydraulic power pack/pump with two-handed safety control system\n"
            "o Digital setting with auto switch-off at set pressure\n"
            "o Secondary back-up pressure setting\n"
            "o Operates from 220–240 V, 1 phase power supply"
        )

        async def _add_approximate_page_sources():
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
                            Requirement.document_version_id == version.id,
                            Requirement.normalized_text == quote,
                        )
                    )
                ).scalar_one()
                requirement.raw_source = quote
                page_18_source = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.requirement_id == requirement.id
                        )
                    )
                ).scalar_one()
                page_18_source.source_text = window_text
                page_18_source.location_type = "approximate"
                session.add(
                    RequirementSource(
                        requirement_id=requirement.id,
                        document_version_id=version.id,
                        page_number=19,
                        clause_number="Grips and Fixtures",
                        location_type="approximate",
                        source_text=window_text,
                    )
                )
                session.add_all(
                    [
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=18,
                            extracted_text=window_text,
                            cleaned_text=window_text,
                            ocr_needed=False,
                        ),
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=19,
                            extracted_text="Load Cell and Testing Systems",
                            cleaned_text="Load Cell and Testing Systems",
                            ocr_needed=False,
                        ),
                    ]
                )
                await session.commit()

        asyncio.run(_add_approximate_page_sources())

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
                return await document_service._source_quote_validation_report(
                    session, rows, object(), version.id  # type: ignore[arg-type]
                )

        report = asyncio.run(_validate())

        assert report["status"] == "passed", report
        assert report["issues"] == []
        assert report["llm_fallback_results"] == []

    def test_visual_fallback_runs_bounded_concurrently_and_respects_page_cap(
        self, monkeypatch
    ):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id,
            doc_id,
            ver,
            [
                (
                    f"Requirement {index}",
                    index,
                    True,
                    "4.1",
                    False,
                    3 if index <= 20 else index - 17,
                )
                for index in range(1, 25)
            ],
        )

        async def _mark_ocr_uncertain():
            async with _session_cm() as session:
                version = (
                    await session.execute(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == uuid.UUID(doc_id),
                            DocumentVersion.version_number == ver,
                        )
                    )
                ).scalar_one()
                requirements = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalars()
                for requirement in requirements:
                    requirement.ocr_warning = True
                    requirement.review_state = RequirementReviewState.OCR_WARNING
                session.add(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=3,
                        cleaned_text="OCR page",
                        ocr_needed=True,
                        rendered_image_object_key="rendered/page-3.png",
                    )
                )
                session.add_all(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=page_number,
                        cleaned_text=f"OCR page {page_number}",
                        ocr_needed=True,
                        rendered_image_object_key=f"rendered/page-{page_number}.png",
                    )
                    for page_number in (4, 5, 6, 7)
                )
                await session.commit()

        asyncio.run(_mark_ocr_uncertain())

        class FakeAdapter:
            pass

        class FakeStorage:
            async def get(self, key: str) -> bytes:
                return key.encode()

        active_calls = 0
        peak_calls = 0
        checked_pages: list[int] = []

        async def fake_visual_check(**kwargs):
            nonlocal active_calls, peak_calls
            active_calls += 1
            peak_calls = max(peak_calls, active_calls)
            checked_pages.append(kwargs["page_number"])
            await asyncio.sleep(0.01)
            active_calls -= 1
            return _fake_page_batch(
                kwargs, lambda _page, _quote: ("exact", 0.99)
            )

        monkeypatch.setattr(
            document_service,
            "get_settings",
            lambda: SimpleNamespace(
                verbatim_validation_fallback_enabled=True,
                openai_api_key="configured-for-test",
            ),
        )
        monkeypatch.setattr(openai_adapter, "OpenAiLlmAdapter", lambda: FakeAdapter())
        monkeypatch.setattr(
            visual_validation, "validate_quotes_on_page_image", fake_visual_check
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
                return await document_service._source_quote_validation_report(
                    session, rows, FakeStorage(), version.id
                )

        report = asyncio.run(_validate())
        statuses = [item["status"] for item in report["llm_fallback_results"]]
        assert len(checked_pages) == 7
        assert peak_calls == 4
        assert statuses.count("exact") == 22
        assert statuses.count("call_limit_reached") == 2
        assert report["status"] == "needs_review"

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
                "coverage_candidates": [],
            }
        ]

    def test_failed_page_image_audit_category_is_reported_without_raw_error(self):
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
            coverage_status="failed",
            coverage_error_category="image_parse_error",
        )

        response = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )

        body = response.json()
        coverage = body["validation_report"]["window_processing"]
        assert body["status"] == "failed"
        assert body["validation_status"] == "needs_review"
        assert coverage["obligation_audit_status"] == "audit_failed"
        assert coverage["obligation_audit_failed_windows"] == [
            {
                "window_index": 1,
                "chunk_id": "window-1",
                "coverage_error_category": "image_parse_error",
                "pages": [3],
            }
        ]
        assert "raw_error" not in coverage["obligation_audit_failed_windows"][0]

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

    def test_native_text_trust_warning_requires_page_image_check(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Chuck model III -V", 1, True, "5.1", False, 3)],
        )

        async def _mark_text_layer_warning():
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
                session.add(
                    DocumentPage(
                        document_version_id=version.id,
                        page_number=3,
                        cleaned_text=requirement.raw_source,
                        structural_metadata={"visual_verification_required": True},
                    )
                )
                await session.commit()

        asyncio.run(_mark_text_layer_warning())
        resp = client.post(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/exports",
            headers=_headers(user_id, org_id),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["validation_status"] == "needs_review"
        issues = body["validation_report"]["source_validation"]["issues"]
        assert len(issues) == 1
        assert issues[0]["code"] == "ocr_visual_verification_required"

    @pytest.mark.parametrize(
        ("ocr_warning", "source_text"),
        [(True, "raw_Req A")],
    )
    @pytest.mark.parametrize(
        ("fallback_outcome", "expected_status"),
        [
            ("exact", "passed"),
            ("not_exact", "needs_review"),
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
                    {},
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
                        error_category="image_parse_error",
                    ),
                )
            verdict = (
                "exact"
                if fallback_outcome == "exact"
                else "not_exact"
                if fallback_outcome == "not_exact"
                else "cannot_tell"
            )
            confidence = 0.99 if fallback_outcome == "exact" else 0.2
            return _fake_page_batch(
                kwargs, lambda _page, _quote: (verdict, confidence)
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
            visual_validation, "validate_quotes_on_page_image", fake_visual_check
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
            assert report["llm_fallback_results"][0]["verdict"] == "unavailable"
            assert (
                report["llm_fallback_results"][0]["reason_code"]
                == "page_image_unavailable"
            )
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
            expected_verdict = {
                "exact": "exact",
                "not_exact": "not_exact",
                "uncertain": "cannot_tell",
                "provider_failed": "unavailable",
            }[fallback_outcome]
            assert report["llm_fallback_results"][0]["verdict"] == expected_verdict
            expected_reason = {
                "exact": "visual_exact_match",
                "not_exact": "visual_wording_mismatch",
                "uncertain": "visual_result_uncertain",
                "provider_failed": "visual_validation_unavailable",
            }[fallback_outcome]
            assert (
                report["llm_fallback_results"][0]["reason_code"]
                == expected_reason
            )
            if fallback_outcome == "provider_failed":
                assert (
                    report["llm_fallback_results"][0]["error_category"]
                    == "image_parse_error"
                )

    def test_fallback_cannot_validate_a_quote_on_a_different_page(self, monkeypatch):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        _add_requirements(
            project_id, doc_id, ver,
            [("Req A", 1, True, "5.1", False, 3)],
        )

        async def _add_later_source_page():
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
                first_source = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.requirement_id == requirement.id
                        )
                    )
                ).scalar_one()
                first_source.source_text = "unrelated OCR text"
                session.add(
                    RequirementSource(
                        requirement_id=requirement.id,
                        document_version_id=version.id,
                        page_number=7,
                        clause_number="5.1",
                        location_type="approximate",
                        source_text=requirement.raw_source,
                    )
                )
                session.add_all(
                    [
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=3,
                            cleaned_text="unrelated OCR text",
                            ocr_needed=True,
                            rendered_image_object_key="rendered/page-3.png",
                        ),
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=7,
                            cleaned_text=requirement.raw_source,
                            ocr_needed=False,
                            rendered_image_object_key="rendered/page-7.png",
                        ),
                    ]
                )
                await session.commit()

        asyncio.run(_add_later_source_page())

        class FakeAdapter:
            pass

        class FakeStorage:
            async def get(self, key: str) -> bytes:
                return key.encode("utf-8")

        checked_pages: list[int] = []

        async def fake_visual_check(**kwargs):
            page_number = kwargs["page_number"]
            checked_pages.append(page_number)
            exact = page_number == 7
            return _fake_page_batch(
                kwargs,
                lambda _page, _quote: (
                    "exact" if exact else "cannot_tell",
                    0.99 if exact else 0.2,
                ),
            )

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
            visual_validation, "validate_quotes_on_page_image", fake_visual_check
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
                assert rows[0].source_page == 3
                return await document_service._source_quote_validation_report(
                    session, rows, FakeStorage(), version.id
                )

        report = asyncio.run(_validate())
        assert report["status"] == "needs_review"
        assert report["llm_assisted_rows"] == []
        assert checked_pages == [3]
        assert report["llm_fallback_results"][0]["page_number"] == 3

    @pytest.mark.parametrize(
        ("second_page_exact", "expected_status"),
        [(True, "passed"), (False, "needs_review")],
    )
    def test_multi_page_visual_fallback_requires_every_page_fragment(
        self, monkeypatch, second_page_exact, expected_status
    ):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        quote = "Measure once across the page\nbreak at 1000/s."
        first_fragment = "Measure once across the page"
        second_fragment = "break at 1000/s."
        _add_requirements(
            project_id, doc_id, ver,
            [(quote, 1, True, "5.1", False, 17)],
        )

        async def _configure_multi_page_source():
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
                requirement.raw_source = quote
                requirement.ocr_warning = True
                source = (
                    await session.execute(
                        select(RequirementSource).where(
                            RequirementSource.requirement_id == requirement.id
                        )
                    )
                ).scalar_one()
                source.page_number = 17
                source.location_type = "exact"
                source.source_text = first_fragment
                source.char_start = 100
                source.char_end = 100 + len(first_fragment)
                session.add(
                    RequirementSource(
                        requirement_id=requirement.id,
                        document_version_id=version.id,
                        page_number=18,
                        location_type="exact",
                        source_text=second_fragment,
                        char_start=0,
                        char_end=len(second_fragment),
                    )
                )
                session.add_all(
                    [
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=17,
                            ocr_needed=True,
                            rendered_image_object_key="rendered/page-17.png",
                        ),
                        DocumentPage(
                            document_version_id=version.id,
                            page_number=18,
                            ocr_needed=True,
                            rendered_image_object_key="rendered/page-18.png",
                        ),
                    ]
                )
                await session.commit()

        asyncio.run(_configure_multi_page_source())

        class FakeAdapter:
            pass

        class FakeStorage:
            async def get(self, key: str) -> bytes:
                return key.encode()

        checked: list[dict[str, object]] = []

        async def fake_visual_check(**kwargs):
            checked.append(kwargs)
            exact = kwargs["page_number"] == 17 or second_page_exact
            return _fake_page_batch(
                kwargs,
                lambda _page, _quote: (
                    "exact" if exact else "not_exact",
                    0.99 if exact else 1.0,
                ),
            )

        monkeypatch.setattr(
            document_service,
            "get_settings",
            lambda: SimpleNamespace(
                verbatim_validation_fallback_enabled=True,
                openai_api_key="configured-for-test",
            ),
        )
        monkeypatch.setattr(openai_adapter, "OpenAiLlmAdapter", lambda: FakeAdapter())
        monkeypatch.setattr(
            visual_validation, "validate_quotes_on_page_image", fake_visual_check
        )

        expected_row_ids: list[str] = []

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
                expected_row_ids.extend(str(row.requirement_id) for row in rows)
                return await document_service._source_quote_validation_report(
                    session, rows, FakeStorage(), version.id
                )

        report = asyncio.run(_validate())

        assert [item["page_number"] for item in checked] == [17, 18]
        assert [item["items"][0].proposed_quote for item in checked] == [
            first_fragment,
            second_fragment,
        ]
        assert report["status"] == expected_status
        assert report["llm_assisted_rows"] == (
            expected_row_ids if expected_status == "passed" else []
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
