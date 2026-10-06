"""Tests for CP54 — ComplianceAssessment model and status semantics.

Covers:
- Enum status semantics (COMPLIANT, NON_COMPLIANT, PARTIAL,
  NOT_DEMONSTRATED, CONFLICT, HUMAN_REVIEW_REQUIRED)
- Assessment versioning (new version on re-assess)
- Missing evidence → NOT_DEMONSTRATED (never NON_COMPLIANT)
- No evidence → NOT_DEMONSTRATED
- No parseable constraint → NOT_DEMONSTRATED
- Evidence exists, no vendor specs → NOT_DEMONSTRATED
- Deterministic comparison produces correct status (COMPLIANT)
- Deterministic comparison produces NON_COMPLIANT (value mismatch)
- Parameter mismatch → HUMAN_REVIEW_REQUIRED
- Human confirmation separates suggestion from final status
- Tenant isolation (cross-org denied)
- Comparison result stored with verbatim source text
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.compliance.service import ComplianceAssessmentService
from tender_compliance_api.db.models import (
    ComplianceAssessment,
    ComplianceStatus,
    ConstraintNormalizationState,
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
    TenderDocument,
    User,
    VendorSpec,
    VendorSpecExtractionMethod,
)

# ---------------------------------------------------------------------------
# Helpers — inlined from test_retrieval to avoid cross-test-module imports
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _setup_project_and_tenant(
    session_cm,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    """Create org, user, membership, project.  Returns (headers, org_id, proj_id)."""

    async def _setup() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="CP54 Test Org"))
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
                    name="CP54 Project",
                    status=ProjectStatus.DRAFT,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    user_id, org_id, project_id = asyncio.run(_setup())
    return _headers(user_id, org_id), org_id, project_id

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_auth(org_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        actor_id=uuid.uuid4(),
        organization_id=org_id,
        roles={"owner"},
    )


def _setup_requirement(
    session_cm, project_id: uuid.UUID,
    raw_source: str = "The operating temperature shall be at least 25 °C.",
) -> uuid.UUID:
    """Create a TenderDocument → DocumentVersion → Requirement."""

    async def _setup() -> uuid.UUID:
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()
        req_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(
                TenderDocument(id=doc_id, project_id=project_id, display_name="tender.pdf")
            )
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=doc_id,
                    version_number=1,
                    stored_object_id=uuid.uuid4(),
                    sha256="abc123",
                    mime_type="application/pdf",
                    size_bytes=1024,
                    processing_status=DocumentProcessingStatus.PARSED,
                )
            )
            session.add(
                Requirement(
                    id=req_id,
                    document_version_id=version_id,
                    promotion_key="req-1",
                    requirement_type="numeric",
                    normalized_text=raw_source,
                    raw_source=raw_source,
                    uncertainty="exact",
                )
            )
            await session.commit()
        return req_id

    return asyncio.run(_setup())


def _setup_evidence_and_vendor_spec(
    session_cm, project_id: uuid.UUID, requirement_id: uuid.UUID,
) -> uuid.UUID:
    """Create OEM doc/version chain, accepted evidence, and a vendor spec."""
    return _setup_evidence_and_vendor_spec_with_value(
        session_cm, project_id, requirement_id,
        value=25.0, unit="°C", parameter="temperature",
        source_text="Operating temperature: 25 °C",
    )


def _setup_evidence_only(
    session_cm, project_id: uuid.UUID, requirement_id: uuid.UUID,
) -> None:
    """Create OEM doc/version chain and accepted evidence, but NO vendor specs."""

    async def _setup() -> None:
        oem_doc_id = uuid.uuid4()
        oem_version_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(
                OemDocument(
                    id=oem_doc_id,
                    project_id=project_id,
                    display_name="datasheet.pdf",
                    document_type=OemDocumentType.DATASHEET,
                    vendor_name="Acme",
                    product_name="X1",
                    product_sku="X1",
                )
            )
            session.add(
                OemDocumentVersion(
                    id=oem_version_id,
                    document_id=oem_doc_id,
                    version_number=1,
                    stored_object_id=uuid.uuid4(),
                    sha256="ghi789",
                    mime_type="application/pdf",
                    size_bytes=512,
                    processing_status=DocumentProcessingStatus.PARSED,
                )
            )
            session.add(
                Evidence(
                    id=uuid.uuid4(),
                    requirement_id=requirement_id,
                    oem_document_version_id=oem_version_id,
                    review_state=EvidenceReviewState.ACCEPTED,
                    score=0.9,
                )
            )
            await session.commit()

    asyncio.run(_setup())


def _setup_evidence_and_vendor_spec_with_value(
    session_cm, project_id: uuid.UUID, requirement_id: uuid.UUID, *,
    value: float, unit: str = "°C", parameter: str = "temperature",
    source_text: str = "Operating temperature: 25 °C",
) -> uuid.UUID:
    """Create OEM doc/version chain, accepted evidence, and a vendor spec."""

    async def _setup() -> uuid.UUID:
        oem_doc_id = uuid.uuid4()
        oem_version_id = uuid.uuid4()
        vendor_spec_id = uuid.uuid4()

        async with session_cm() as session:
            session.add(
                OemDocument(
                    id=oem_doc_id,
                    project_id=project_id,
                    display_name="datasheet.pdf",
                    document_type=OemDocumentType.DATASHEET,
                    vendor_name="Acme",
                    product_name="X1",
                    product_sku="X1",
                )
            )
            session.add(
                OemDocumentVersion(
                    id=oem_version_id,
                    document_id=oem_doc_id,
                    version_number=1,
                    stored_object_id=uuid.uuid4(),
                    sha256="ghi789",
                    mime_type="application/pdf",
                    size_bytes=512,
                    processing_status=DocumentProcessingStatus.PARSED,
                )
            )
            evidence_id = uuid.uuid4()
            session.add(
                Evidence(
                    id=evidence_id,
                    requirement_id=requirement_id,
                    oem_document_version_id=oem_version_id,
                    review_state=EvidenceReviewState.ACCEPTED,
                    score=0.9,
                )
            )
            session.add(
                VendorSpec(
                    id=vendor_spec_id,
                    evidence_id=evidence_id,
                    requirement_id=requirement_id,
                    oem_document_version_id=oem_version_id,
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
            )
            await session.commit()
        return vendor_spec_id

    return asyncio.run(_setup())


def _run_assess(
    session_cm, auth: AuthContext, project_id: uuid.UUID, req_id: uuid.UUID,
) -> ComplianceAssessment:
    """Run assess_requirement and return the result."""

    async def _run() -> ComplianceAssessment | None:
        async with session_cm() as session:
            svc = ComplianceAssessmentService(session)
            return await svc.assess_requirement(
                auth=auth, project_id=project_id, requirement_id=req_id,
            )

    result = asyncio.run(_run())
    assert result is not None
    return result


# ---------------------------------------------------------------------------
# Status semantics
# ---------------------------------------------------------------------------


class TestComplianceStatusEnum:
    """Verify the six product-defined statuses exist."""

    def test_all_statuses_present(self) -> None:
        assert ComplianceStatus.COMPLIANT == "compliant"
        assert ComplianceStatus.NON_COMPLIANT == "non_compliant"
        assert ComplianceStatus.PARTIAL == "partial"
        assert ComplianceStatus.NOT_DEMONSTRATED == "not_demonstrated"
        assert ComplianceStatus.CONFLICT == "conflict"
        assert ComplianceStatus.HUMAN_REVIEW_REQUIRED == "human_review_required"

    def test_is_str_enum(self) -> None:
        assert isinstance(ComplianceStatus.COMPLIANT, str)
        assert ComplianceStatus.COMPLIANT.value == "compliant"


# ---------------------------------------------------------------------------
# No evidence → NOT_DEMONSTRATED
# ---------------------------------------------------------------------------


class TestNoEvidenceNotDemonstrated:
    """Missing evidence → NOT_DEMONSTRATED, never NON_COMPLIANT."""

    def test_no_evidence_creates_not_demonstrated(self, session_cm) -> None:
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(session_cm, project_id)
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.status is ComplianceStatus.NOT_DEMONSTRATED
        assert assessment.reason_code == "no_evidence_found"
        assert assessment.is_confirmed_by_human is False

    def test_no_evidence_stores_no_comparison_result(self, session_cm) -> None:
        """With no evidence, comparison_result_json is None (nothing fabricated)."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(session_cm, project_id)
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.status is ComplianceStatus.NOT_DEMONSTRATED
        assert assessment.comparison_result_json is None


# ---------------------------------------------------------------------------
# Assessment versioning
# ---------------------------------------------------------------------------


class TestAssessmentVersioning:
    """New assessment → incremented version number (append-only)."""

    def test_first_assessment_is_version_1(self, session_cm) -> None:
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(session_cm, project_id)
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.assessment_version == 1

    def test_re_assess_increments_version(self, session_cm) -> None:
        """Re-running assessment creates a new version (append-only)."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The operating temperature shall be at least 25 °C.",
        )
        auth = _make_auth(org_id)

        async def _run() -> tuple[ComplianceAssessment, ComplianceAssessment]:
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                first = await svc.assess_requirement(
                    auth=auth, project_id=project_id, requirement_id=req_id,
                )
                second = await svc.assess_requirement(
                    auth=auth, project_id=project_id, requirement_id=req_id,
                )
                return first, second

        first, second = asyncio.run(_run())
        assert first is not None
        assert second is not None
        assert first.assessment_version == 1
        assert second.assessment_version == 2
        assert first.id != second.id  # new row, not modified


# ---------------------------------------------------------------------------
# Deterministic comparison produces correct status
# ---------------------------------------------------------------------------


class TestDeterministicAssessment:
    """Assessment correctly maps ComparisonResult to ComplianceStatus."""

    def test_matching_vendor_spec_compliant(self, session_cm) -> None:
        """Tender 'temperature ≥ 25 °C' + vendor '25 °C' → COMPLIANT."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The operating temperature shall be at least 25 °C.",
        )
        _setup_evidence_and_vendor_spec(session_cm, project_id, req_id)
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.status is ComplianceStatus.COMPLIANT
        assert assessment.comparison_result_json["verdict"] == "match"

    def test_mismatch_vendor_spec_non_compliant(self, session_cm) -> None:
        """Vendor value below the required minimum → NON_COMPLIANT."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The operating temperature shall be at least 50 °C.",
        )
        # Vendor only provides 25 °C — below the 50 °C requirement.
        _setup_evidence_and_vendor_spec_with_value(
            session_cm, project_id, req_id,
            value=25.0, unit="°C",
            source_text="Operating temperature: 25 °C",
        )
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.status is ComplianceStatus.NON_COMPLIANT
        assert assessment.comparison_result_json["verdict"] == "mismatch"

    def test_parameter_mismatch_human_review(self, session_cm) -> None:
        """Accuracy vs resolution with same unit → INCOMPARABLE → HUMAN_REVIEW."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The accuracy shall be at least 99 %.",
        )
        _setup_evidence_and_vendor_spec_with_value(
            session_cm, project_id, req_id,
            value=99.0, unit="%", parameter="resolution",
            source_text="Resolution: 99 %",
        )
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.status is ComplianceStatus.HUMAN_REVIEW_REQUIRED
        assert assessment.comparison_result_json["verdict"] == "incomparable"

    def test_no_parseable_constraint(self, session_cm) -> None:
        """Requirement with no numeric constraint → NOT_DEMONSTRATED."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The product shall be CE marked.",
        )
        _setup_evidence_and_vendor_spec(session_cm, project_id, req_id)
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.status is ComplianceStatus.NOT_DEMONSTRATED
        assert assessment.reason_code == "no_constraint_parsed"

    def test_evidence_no_vendor_specs(self, session_cm) -> None:
        """Evidence exists but no vendor specs → NOT_DEMONSTRATED."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The operating temperature shall be at least 25 °C.",
        )
        _setup_evidence_only(session_cm, project_id, req_id)
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.status is ComplianceStatus.NOT_DEMONSTRATED
        assert assessment.reason_code == "no_matching_vendor_spec"

    def test_comparison_result_stores_verbatim_source(self, session_cm) -> None:
        """The comparison_result_json stores verbatim source text."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The operating temperature shall be at least 25 °C.",
        )
        _setup_evidence_and_vendor_spec(session_cm, project_id, req_id)
        auth = _make_auth(org_id)

        assessment = _run_assess(session_cm, auth, project_id, req_id)
        result = assessment.comparison_result_json
        assert result is not None
        tender_text = result.get("tender_text") or ""
        vendor_text = result.get("vendor_text") or ""
        assert "25" in tender_text
        assert "25" in vendor_text


# ---------------------------------------------------------------------------
# Human confirmation
# ---------------------------------------------------------------------------


class TestHumanConfirmation:
    """Human confirmation separates system suggestion from final status."""

    def test_confirm_sets_human_flag(self, session_cm) -> None:
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(
            session_cm, project_id,
            raw_source="The operating temperature shall be at least 25 °C.",
        )
        _setup_evidence_and_vendor_spec(session_cm, project_id, req_id)
        auth = _make_auth(org_id)

        async def _run() -> ComplianceAssessment:
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=project_id, requirement_id=req_id,
                )
                assert assessment is not None
                assert assessment.is_confirmed_by_human is False
                confirmed = await svc.confirm_assessment(
                    auth=auth, assessment_id=assessment.id,
                )
                assert confirmed is not None
                assert confirmed.is_confirmed_by_human is True
                assert confirmed.reviewer_id == auth.actor_id
                assert confirmed.reviewed_at is not None
                return confirmed

        confirmed = asyncio.run(_run())
        assert confirmed.is_confirmed_by_human is True

    def test_confirm_sets_status_to_suggested(self, session_cm) -> None:
        """After confirmation, status == suggested_status."""
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(session_cm, project_id)
        _setup_evidence_and_vendor_spec(session_cm, project_id, req_id)
        auth = _make_auth(org_id)

        async def _run() -> tuple[ComplianceAssessment, ComplianceAssessment]:
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=project_id, requirement_id=req_id,
                )
                assert assessment is not None
                original_suggested = assessment.suggested_status
                confirmed = await svc.confirm_assessment(
                    auth=auth, assessment_id=assessment.id,
                )
                assert confirmed is not None
                assert confirmed.status == original_suggested
                return assessment, confirmed

        assessment, confirmed = asyncio.run(_run())
        assert assessment.suggested_status == confirmed.status


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Cross-org access is denied."""

    def test_cross_tenant_assess_returns_none(self, session_cm) -> None:
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(session_cm, project_id)
        other_auth = _make_auth(uuid.uuid4())

        async def _run() -> ComplianceAssessment | None:
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                return await svc.assess_requirement(
                    auth=other_auth, project_id=project_id, requirement_id=req_id,
                )

        assessment = asyncio.run(_run())
        assert assessment is None


# ---------------------------------------------------------------------------
# Regression: Phase-2 mutations must commit so they survive across sessions.
#
# Before the service-level commit was added, assess_requirement flushed the
# row in-session but never committed; the returned object was valid, so the
# same-session unit tests passed — yet the live routes returned 201 while
# `compliance_assessments` stayed empty, making final-matrix show status=None.
# ---------------------------------------------------------------------------


class TestAssessmentPersistenceAcrossSessions:
    """assess_requirement must persist (HTTP 201 -> row survives the request)."""

    def test_assess_persists_for_subsequent_session(self, session_cm) -> None:
        _, org_id, project_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(session_cm, project_id)
        _setup_evidence_and_vendor_spec(session_cm, project_id, req_id)
        auth = _make_auth(org_id)

        # Runs in one request/session (no test-level commit).
        assessment = _run_assess(session_cm, auth, project_id, req_id)
        assert assessment.id is not None

        # A *different* session (the next request) must still see the row.
        async def _count() -> int:
            async with session_cm() as s:
                rows = (
                    await s.execute(
                        select(ComplianceAssessment).where(
                            ComplianceAssessment.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                return len(rows)

        count = asyncio.run(_count())
        assert count == 1, f"assessment not persisted across sessions (got {count})"
