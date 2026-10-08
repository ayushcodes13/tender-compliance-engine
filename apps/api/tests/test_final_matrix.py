"""Tests for CP59 — Final compliance matrix and submission projection.

Covers:
- Phase 1 columns preserved in the final matrix
- Requirements with no evidence: Phase 2 fields are None (not fabricated)
- Evidence + vendor spec provenance linked per row
- Assessment status reflects system suggestion (COMPLIANT)
- Assessment status reflects human overrides (NON_COMPLIANT)
- Conflicts, clarifications, and deviations surfaced per row
- Resolved conflicts do not set has_unresolved_conflict
- Superseded requirements excluded
- Deterministic ordering (display_order NULLS LAST)
- Tenant isolation: cross-org access returns 404
- Empty document version returns empty list
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.compliance.missing_evidence import (
    ClarificationContext,
    MissingEvidenceService,
)
from tender_compliance_api.compliance.service import ComplianceAssessmentService
from tender_compliance_api.db.models import (
    ComplianceStatus,
    Conflict,
    ConflictResolution,
    ConstraintNormalizationState,
    Deviation,
    DeviationStatus,
    DeviationType,
    DocumentProcessingStatus,
    DocumentVersion,
    Evidence,
    EvidenceReviewState,
    Membership,
    OemDocument,
    OemDocumentType,
    OemDocumentVersion,
    Organization,
    Project,
    ProjectStatus,
    Requirement,
    RequirementSource,
    TenderDocument,
    User,
    VendorSpec,
    VendorSpecExtractionMethod,
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
    """Set up org + user + membership + project + document version."""

    async def _setup():
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with _session_cm() as session:
            session.add(Organization(id=org_id, name="CP59 Test Org"))
            session.add(
                User(
                    id=user_id,
                    auth_provider="dev",
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
                    id=project_id,
                    organization_id=org_id,
                    name="CP59 Project",
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


def _make_auth(user_id: uuid.UUID, org_id: uuid.UUID) -> AuthContext:
    return AuthContext(actor_id=user_id, organization_id=org_id, roles={"owner"})


def _add_requirement(
    session,
    version_id: uuid.UUID,
    normalized: str,
    *,
    display_order: int | None = None,
    superseded: bool = False,
    clause: str | None = None,
    uncertainty: str = "exact",
) -> Requirement:
    req = Requirement(
        document_version_id=version_id,
        promotion_key=f"pk-{uuid.uuid4().hex[:8]}",
        requirement_type="numeric",
        normalized_text=normalized,
        raw_source=normalized,
        uncertainty=uncertainty,
        ocr_warning=False,
        display_order=display_order,
        mandatory=None,
        superseded=superseded,
        clause_number=clause,
    )
    session.add(req)
    return req


async def _add_evidence_and_vendor_spec(
    session,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    *,
    value: float = 25.0,
    unit: str = "°C",
    parameter: str = "temperature",
    source_text: str = "Operating temperature: 25 °C",
) -> None:
    oem_doc = OemDocument(
        project_id=project_id,
        display_name="datasheet.pdf",
        document_type=OemDocumentType.DATASHEET,
        vendor_name="Acme",
        product_name="X1",
        product_sku="X1",
    )
    session.add(oem_doc)
    await session.flush()
    oem_ver = OemDocumentVersion(
        document_id=oem_doc.id,
        version_number=1,
        stored_object_id=uuid.uuid4(),
        sha256="ghi789",
        mime_type="application/pdf",
        size_bytes=512,
        processing_status=DocumentProcessingStatus.PARSED,
    )
    session.add(oem_ver)
    await session.flush()
    evidence = Evidence(
        requirement_id=requirement_id,
        oem_document_version_id=oem_ver.id,
        review_state=EvidenceReviewState.ACCEPTED,
        score=0.9,
    )
    session.add(evidence)
    await session.flush()
    vs = VendorSpec(
        evidence_id=evidence.id,
        requirement_id=requirement_id,
        oem_document_version_id=oem_ver.id,
        parameter=parameter,
        value=value,
        unit=unit,
        source_text=source_text,
        source_page_number=1,
        extraction_method=VendorSpecExtractionMethod.DETERMINISTIC,
        extraction_version="cp52-deterministic-v1",
        normalization_state=ConstraintNormalizationState.SAFE,
        location_type="exact",
    )
    session.add(vs)


def _add_conflict(
    session,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    *,
    resolution: ConflictResolution = ConflictResolution.UNRESOLVED,
) -> None:
    session.add(
        Conflict(
            id=uuid.uuid4(),
            project_id=project_id,
            requirement_id=requirement_id,
            conflict_type="parameter_value",
            parameter="temperature",
            entity=None,
            sources=[
                {"evidence_id": str(uuid.uuid4()), "source_text": "25 °C"},
                {"evidence_id": str(uuid.uuid4()), "source_text": "30 °C"},
            ],
            tender_claim="The operating temperature shall be at least 25 °C.",
            resolution=resolution,
        )
    )


def _add_deviation(
    session,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    *,
    status: DeviationStatus = DeviationStatus.ACCEPTED,
) -> None:
    session.add(
        Deviation(
            id=uuid.uuid4(),
            project_id=project_id,
            requirement_id=requirement_id,
            deviation_type=DeviationType.VALUE,
            original_requirement="Shall operate at 25 °C.",
            proposed_alternative="Propose 30 °C.",
            rationale="Component availability.",
            status=status,
        )
    )


def _version_from_setup(doc_id: str, ver: int):
    async def _lookup():
        async with _session_cm() as session:
            result = await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == uuid.UUID(doc_id),
                    DocumentVersion.version_number == ver,
                )
            )
            return result.scalar_one()
    return asyncio.run(_lookup())


# ---------------------------------------------------------------------------
# Phase 1 column preservation
# ---------------------------------------------------------------------------


class TestPhase1Columns:
    def test_phase1_columns_preserved(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id, "req1 text", display_order=1
                )
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        row = rows[0]
        assert row.serial == 1
        assert row.tender_requirement == "req1 text"
        assert row.review_status == "unreviewed"
        assert row.ocr_warning is False
        assert row.normalized_text == "req1 text"
        assert row.raw_source == "req1 text"


# ---------------------------------------------------------------------------
# Missing evidence — honest, not fabricated
# ---------------------------------------------------------------------------


class TestMissingEvidence:
    def test_no_evidence_means_none(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id, "req without evidence", display_order=1
                )
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        row = rows[0]
        assert row.evidence_id is None
        assert row.vendor_spec_value is None
        assert row.vendor_spec_unit is None
        assert row.assessment_status is None
        assert row.assessment_suggested_status is None
        assert row.assessment_reason_code is None
        assert row.has_unresolved_conflict is False
        assert row.clarification_statuses == []
        assert row.deviation_statuses == []


# ---------------------------------------------------------------------------
# Evidence + vendor spec
# ---------------------------------------------------------------------------


class TestEvidenceAndVendorSpec:
    def test_evidence_and_vendor_spec_populated(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id, "temperature req", display_order=1
                )
                await session.flush()
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar()
                await _add_evidence_and_vendor_spec(
                    session, project_id, req.id
                )


# ---------------------------------------------------------------------------
# Assessment status
# ---------------------------------------------------------------------------


class TestAssessmentStatus:
    def test_system_assessment_populated(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)
        auth = _make_auth(user_id, org_id)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id,
                    "The operating temperature shall be at least 25 °C.",
                    display_order=1,
                )
                await session.flush()
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar()
                await _add_evidence_and_vendor_spec(session, project_id, req.id)
                await session.commit()
                # Assess.
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=project_id, requirement_id=req.id
                )
                await session.commit()
                return assessment

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        row = rows[0]
        assert row.assessment_status == "compliant"
        assert row.assessment_suggested_status == "compliant"
        assert row.assessment_reason_code is not None
        assert row.assessment_is_confirmed is False
        assert row.assessment_version == 1

    def test_human_override_reflected(self):
        """Override to NON_COMPLIANT is reflected in the final matrix."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)
        auth = _make_auth(user_id, org_id)

        async def _setup_and_override():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id,
                    "The operating temperature shall be at least 25 °C.",
                    display_order=1,
                )
                await session.flush()
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar()
                await _add_evidence_and_vendor_spec(session, project_id, req.id)
                await session.commit()
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=project_id, requirement_id=req.id
                )
                assert assessment is not None
                overridden = await svc.override_assessment(
                    auth=auth,
                    project_id=project_id,
                    assessment_id=assessment.id,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason="Physical testing showed 24.5 °C under load.",
                )
                assert overridden is not None
                await session.commit()
                return assessment, overridden

        asyncio.run(_setup_and_override())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        row = rows[0]
        assert row.assessment_status == "non_compliant"
        assert row.assessment_suggested_status == "compliant"
        assert row.assessment_is_confirmed is True
        assert row.assessment_version == 2
        assert row.assessment_reviewer_id == auth.actor_id
        assert row.assessment_reason_code == "human_override"


# ---------------------------------------------------------------------------
# Conflict / clarification / deviation summary
# ---------------------------------------------------------------------------


class TestReviewStateSummary:
    def test_conflict_clarification_deviation_visible(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)
        auth = _make_auth(user_id, org_id)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id,
                    "The operating temperature shall be at least 25 °C.",
                    display_order=1,
                )
                await session.flush()
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar()
                await _add_evidence_and_vendor_spec(session, project_id, req.id)
                _add_conflict(
                    session, project_id, req.id,
                    resolution=ConflictResolution.UNRESOLVED,
                )
                # Add assessment.
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=project_id, requirement_id=req.id
                )
                await session.commit()
                # Add clarification and deviation.
                clar_svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                await clar_svc.create_clarification(
                    auth=auth,
                    project_id=project_id,
                    question="Need clarification on temperature range.",
                    context=ClarificationContext(
                        reason="missing_evidence", parameter="temperature"
                    ),
                    requirement_id=req.id,
                )
                session.add(
                    Deviation(
                        id=uuid.uuid4(),
                        project_id=project_id,
                        requirement_id=req.id,
                        deviation_type=DeviationType.VALUE,
                        original_requirement="Shall operate at 25 °C.",
                        proposed_alternative="Propose 30 °C.",
                        rationale="Component availability.",
                        status=DeviationStatus.ACCEPTED,
                    )
                )
                await session.commit()
                return assessment

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        row = rows[0]
        assert row.has_unresolved_conflict is True
        assert row.clarification_statuses == ["pending"]
        assert row.deviation_statuses == ["accepted"]

    def test_resolved_conflict_not_flagged(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id,
                    "The operating temperature shall be at least 25 °C.",
                    display_order=1,
                )
                await session.flush()
                req = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id
                        )
                    )
                ).scalar()
                _add_conflict(
                    session, project_id, req.id,
                    resolution=ConflictResolution.ACCEPTED,
                )
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        assert rows[0].has_unresolved_conflict is False


# ---------------------------------------------------------------------------
# Superseded / ordering
# ---------------------------------------------------------------------------


class TestSupersededAndOrdering:
    def test_superseded_excluded(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(session, version.id, "active", display_order=1)
                _add_requirement(
                    session, version.id, "superseded", display_order=2,
                    superseded=True,
                )
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 1
        assert rows[0].tender_requirement == "active"

    def test_display_order_drives_order(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(session, version.id, "req_2", display_order=2)
                _add_requirement(session, version.id, "req_1", display_order=1)
                await session.commit()

        asyncio.run(_setup())

        from tender_compliance_api.matrix.projection import (
            project_final_matrix_rows,
        )

        async def _project():
            async with _session_cm() as session:
                return await project_final_matrix_rows(session, version.id)

        rows = asyncio.run(_project())
        assert len(rows) == 2
        assert rows[0].tender_requirement == "req_1"
        assert rows[1].tender_requirement == "req_2"


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestFinalMatrixEndpoint:
    def test_final_matrix_endpoint_returns_rows(self):
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        version = _version_from_setup(doc_id, ver)
        auth = _make_auth(user_id, org_id)
        source_anchor_id = uuid.uuid4()

        async def _setup():
            async with _session_cm() as session:
                _add_requirement(
                    session, version.id, "The operating temperature shall be at least 25 °C.",
                    display_order=1,
                )
                _add_requirement(
                    session, version.id, "Humidity requirement.", display_order=2,
                    superseded=True,
                )
                await session.flush()
                reqs = (
                    await session.execute(
                        select(Requirement).where(
                            Requirement.document_version_id == version.id,
                            Requirement.superseded.is_(False),
                        )
                    )
                ).scalars().all()
                for r in reqs:
                    await _add_evidence_and_vendor_spec(session, project_id, r.id)
                session.add(
                    RequirementSource(
                        id=source_anchor_id,
                        requirement_id=reqs[0].id,
                        document_version_id=version.id,
                        page_number=12,
                        clause_number="4.2",
                        char_start=0,
                        char_end=len(reqs[0].raw_source),
                        location_type="exact",
                        source_text=reqs[0].raw_source,
                    )
                )
                session.add(
                    RequirementSource(
                        id=uuid.uuid4(),
                        requirement_id=reqs[0].id,
                        document_version_id=version.id,
                        page_number=14,
                        clause_number="4.3",
                        location_type="approximate",
                        source_text=reqs[0].raw_source,
                    )
                )
                await session.commit()
                # Assess each.
                svc = ComplianceAssessmentService(session)
                for r in reqs:
                    await svc.assess_requirement(
                        auth=auth, project_id=project_id, requirement_id=r.id
                    )
                await session.commit()

        asyncio.run(_setup())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/final-matrix",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1  # only the active requirement
        assert data[0]["tender_requirement"] == "The operating temperature shall be at least 25 °C."
        assert data[0]["serial"] == 1
        assert data[0]["evidence_id"] is not None
        assert data[0]["assessment_status"] == "compliant"
        assert data[0]["has_unresolved_conflict"] is False
        # Phase 1 columns preserved.
        assert data[0]["raw_source"] == "The operating temperature shall be at least 25 °C."
        assert data[0]["source_page"] == 12
        assert data[0]["source_anchor_id"] == str(source_anchor_id)

    def test_final_matrix_tenant_isolation(self):
        """Cross-org access to final matrix returns 404."""
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
                        organization_id=other_org,
                        user_id=other_user,
                        role="owner",
                    )
                )
                await session.commit()
            return other_user, other_org

        other_user, other_org = asyncio.run(_other_org())

        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/final-matrix",
            headers=_headers(other_user, other_org),
        )
        assert resp.status_code == 404

    def test_final_matrix_empty_version(self):
        """A document version with no requirements returns an empty list."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        # No requirements added.
        resp = client.get(
            f"/projects/{project_id}/documents/{doc_id}/versions/{ver}/final-matrix",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_final_matrix_not_found(self):
        """Non-existent document returns 404."""
        user_id, org_id, project_id, doc_id, ver = _build_org_project()
        resp = client.get(
            f"/projects/{project_id}/documents/{uuid.uuid4()}"
            f"/versions/{ver}/final-matrix",
            headers=_headers(user_id, org_id),
        )
        assert resp.status_code == 404
