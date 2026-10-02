"""Tests for CP58 — Human compliance review and audit.

Covers:
- Override assessment creates a new version (append-only), preserves original
- Override with same status as suggested raises ValueError
- Override unknown assessment returns None
- Override records audit comment
- Reopen confirmed assessment creates new unconfirmed version
- Reopen unconfirmed assessment raises ValueError
- Add comment (tenant-scoped, append-only)
- List comments ordered by created_at
- Combined review view (assessment + conflicts + clarifications + deviations)
- Cross-tenant denial for override / comments / review
"""

from __future__ import annotations

import asyncio
import uuid

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.compliance.missing_evidence import (
    ClarificationContext,
    MissingEvidenceService,
)
from tender_compliance_api.compliance.service import ComplianceAssessmentService
from tender_compliance_api.db.models import (
    AssessmentCommentType,
    ComplianceAssessment,
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
    TenderDocument,
    User,
    VendorSpec,
    VendorSpecExtractionMethod,
)

# ---------------------------------------------------------------------------
# Helpers — modeled on test_compliance_assessment.py and test_missing_evidence.py
# ---------------------------------------------------------------------------


def _setup_project_and_tenant(
    session_cm,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create org, user, membership, project.  Returns (user_id, org_id, proj_id)."""

    async def _setup():
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="CP58 Test Org"))
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
                    name="CP58 Project",
                    status=ProjectStatus.DRAFT,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


def _make_auth(user_id: uuid.UUID, org_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        actor_id=user_id,
        organization_id=org_id,
        roles={"owner"},
    )


def _setup_requirement(
    session_cm,
    project_id: uuid.UUID,
    raw_source: str = "The operating temperature shall be at least 25 °C.",
) -> uuid.UUID:
    """Create TenderDocument → DocumentVersion → Requirement."""

    async def _setup() -> uuid.UUID:
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()
        req_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(
                TenderDocument(
                    id=doc_id,
                    project_id=project_id,
                    display_name="tender.pdf",
                )
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
                    promotion_key="req-cp58-1",
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
    session_cm,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    *,
    value: float = 25.0,
    unit: str = "°C",
    parameter: str = "temperature",
    source_text: str = "Operating temperature: 25 °C",
) -> uuid.UUID:
    """Create OEM doc/version chain, accepted evidence, and a matching vendor spec."""

    async def _setup() -> uuid.UUID:
        oem_doc_id = uuid.uuid4()
        oem_version_id = uuid.uuid4()
        evidence_id = uuid.uuid4()
        vs_id = uuid.uuid4()

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
                    id=evidence_id,
                    requirement_id=requirement_id,
                    oem_document_version_id=oem_version_id,
                    review_state=EvidenceReviewState.ACCEPTED,
                    score=0.9,
                )
            )
            session.add(
                VendorSpec(
                    id=vs_id,
                    evidence_id=evidence_id,
                    requirement_id=requirement_id,
                    oem_document_version_id=oem_version_id,
                    parameter=parameter,
                    entity=None,
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
        return evidence_id

    return asyncio.run(_setup())


def _setup_conflict(
    session_cm,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    *,
    conflict_type: str = "parameter_value",
    parameter: str = "temperature",
) -> uuid.UUID:
    """Create a Conflict record directly for the requirement."""

    conflict_id = uuid.uuid4()

    async def _setup() -> uuid.UUID:
        async with session_cm() as session:
            session.add(
                Conflict(
                    id=conflict_id,
                    project_id=project_id,
                    requirement_id=requirement_id,
                    conflict_type=conflict_type,
                    parameter=parameter,
                    entity=None,
                    sources=[{"evidence_id": str(uuid.uuid4()), "source_text": "25 °C"},
                             {"evidence_id": str(uuid.uuid4()), "source_text": "30 °C"}],
                    tender_claim="The operating temperature shall be at least 25 °C.",
                    resolution=ConflictResolution.UNRESOLVED,
                )
            )
            await session.commit()
        return conflict_id

    return asyncio.run(_setup())


def _setup_clarification(
    session_cm,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    requirement_id: uuid.UUID,
) -> uuid.UUID:
    """Create a clarification request for the requirement."""

    async def _setup() -> uuid.UUID:
        async with session_cm() as session:
            svc = MissingEvidenceService(
                db=session, audit=AuditService(session)
            )
            auth = _make_auth(user_id, org_id)
            cr = await svc.create_clarification(
                auth=auth,
                project_id=project_id,
                question="Need clarification on temperature range.",
                context=ClarificationContext(
                    reason="missing_evidence", parameter="temperature"
                ),
                requirement_id=requirement_id,
            )
            await session.commit()
            return cr.id

    return asyncio.run(_setup())


def _setup_deviation(
    session_cm,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
) -> uuid.UUID:
    """Create a deviation for the requirement. Returns the deviation ID."""

    dev_id = uuid.uuid4()

    async def _setup() -> None:
        async with session_cm() as session:
            session.add(
                Deviation(
                    id=dev_id,
                    project_id=project_id,
                    requirement_id=requirement_id,
                    deviation_type=DeviationType.VALUE,
                    original_requirement="Shall operate at 25 °C.",
                    proposed_alternative="Propose 30 °C.",
                    rationale="Component availability.",
                    status=DeviationStatus.PROPOSED,
                )
            )
            await session.commit()

    asyncio.run(_setup())
    return dev_id


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
# Override
# ---------------------------------------------------------------------------


class TestOverrideAssessment:
    """Human override creates a new append-only version."""

    def test_override_creates_new_version_preserves_original(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                # System assessment: COMPLIANT (25 >= 25).
                original = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert original is not None
                assert original.status == ComplianceStatus.COMPLIANT
                assert original.is_confirmed_by_human is False
                # Human overrides to NON_COMPLIANT with a reason.
                overridden = await svc.override_assessment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=original.id,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason="Physical testing showed 24.5 °C under load.",
                )
                return original, overridden

        original, overridden = asyncio.run(_run())
        assert overridden is not None
        # New version with incremented version number.
        assert overridden.assessment_version == original.assessment_version + 1
        # suggested_status preserved from the system suggestion.
        assert overridden.suggested_status == ComplianceStatus.COMPLIANT
        # status is the human's override.
        assert overridden.status == ComplianceStatus.NON_COMPLIANT
        assert overridden.is_confirmed_by_human is True
        assert overridden.reviewer_id == auth.actor_id
        assert overridden.reason_code == "human_override"
        assert overridden.reason_text == "Physical testing showed 24.5 °C under load."

    def test_override_same_status_raises(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert assessment is not None
                try:
                    await svc.override_assessment(
                        auth=auth,
                        project_id=proj_id,
                        assessment_id=assessment.id,
                        status=assessment.suggested_status,
                        reason="Trying to override with same status.",
                    )
                    return "no_error"
                except ValueError:
                    return "value_error"

        result = asyncio.run(_run())
        assert result == "value_error"

    def test_override_unknown_returns_none(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                result = await svc.override_assessment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=uuid.uuid4(),
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason="No assessment exists.",
                )
                return result

        result = asyncio.run(_run())
        assert result is None

    def test_override_records_audit_comment(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert assessment is not None
                overridden = await svc.override_assessment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=assessment.id,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason="Override reason here.",
                )
                # The override should have created a comment.
                comments = await svc.list_comments(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=overridden.id,
                )
                return comments

        comments = asyncio.run(_run())
        assert len(comments) == 1
        assert comments[0].comment_type == AssessmentCommentType.OVERRIDE_REASON
        assert comments[0].comment == "Override reason here."

    def test_override_change_evidence(self, session_cm):
        """Override can re-link to a different evidence item."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert assessment is not None
                # Set up a second evidence item.
                ev2_id = uuid.uuid4()
                session.add(
                    Evidence(
                        id=ev2_id,
                        requirement_id=req_id,
                        oem_document_version_id=uuid.uuid4(),
                        review_state=EvidenceReviewState.ACCEPTED,
                        score=0.5,
                    )
                )
                await session.flush()
                overridden = await svc.override_assessment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=assessment.id,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason="Re-linked evidence.",
                    evidence_id=ev2_id,
                )
                return assessment, overridden, ev2_id

        assessment, overridden, ev2_id = asyncio.run(_run())
        assert overridden is not None
        assert overridden.evidence_id == ev2_id
        assert overridden.evidence_id != assessment.evidence_id


# ---------------------------------------------------------------------------
# Reopen
# ---------------------------------------------------------------------------


class TestReopenAssessment:
    """Reopen creates a new unconfirmed version, preserving the confirmed one."""

    def test_reopen_confirmed(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert assessment is not None
                confirmed = await svc.confirm_assessment(
                    auth=auth, assessment_id=assessment.id
                )
                assert confirmed is not None
                assert confirmed.is_confirmed_by_human is True
                # Reopen.
                reopened = await svc.reopen_assessment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=confirmed.id,
                    reason="New evidence discovered.",
                )
                return confirmed, reopened

        confirmed, reopened = asyncio.run(_run())
        assert reopened is not None
        assert reopened.assessment_version == confirmed.assessment_version + 1
        assert reopened.is_confirmed_by_human is False
        assert reopened.status == reopened.suggested_status
        assert reopened.reason_code == "reopened"

    def test_reopen_unconfirmed_raises(self, session_cm):
        """Cannot reopen an assessment that was never confirmed."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert assessment is not None
                try:
                    await svc.reopen_assessment(
                        auth=auth,
                        project_id=proj_id,
                        assessment_id=assessment.id,
                    )
                    return "no_error"
                except ValueError:
                    return "value_error"

        result = asyncio.run(_run())
        assert result == "value_error"


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class TestComments:
    """Add and list assessment comments."""

    def test_add_and_list_comment(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert assessment is not None
                c1 = await svc.add_comment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=assessment.id,
                    comment="First note.",
                    comment_type=AssessmentCommentType.COMMENT,
                )
                c2 = await svc.add_comment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=assessment.id,
                    comment="Second note.",
                    comment_type=AssessmentCommentType.NOTE,
                )
                comments = await svc.list_comments(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=assessment.id,
                )
                return c1, c2, comments

        c1, c2, comments = asyncio.run(_run())
        assert len(comments) == 2
        # Ordered by created_at ascending.
        assert comments[0].comment == "First note."
        assert comments[1].comment == "Second note."
        assert comments[0].assessment_version == c1.assessment_version

    def test_comment_unknown_assessment_returns_none(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                result = await svc.add_comment(
                    auth=auth,
                    project_id=proj_id,
                    assessment_id=uuid.uuid4(),
                    comment="Orphan comment.",
                )
                return result

        result = asyncio.run(_run())
        assert result is None


# ---------------------------------------------------------------------------
# Combined review view
# ---------------------------------------------------------------------------


class TestRequirementReview:
    """get_requirement_review returns assessment + conflicts + clarifications
    + deviations in one query."""

    def test_combined_review_view(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_id, req_id)
        _setup_conflict(
            session_cm, proj_id, req_id,
            parameter="temperature",
        )
        _setup_clarification(
            session_cm, proj_id, user_id, org_id, req_id
        )
        _setup_deviation(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                # Assess to create the assessment.
                assessment = await svc.assess_requirement(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                assert assessment is not None
                # Get the combined review view.
                review = await svc.get_requirement_review(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                return review

        review = asyncio.run(_run())
        assert review is not None
        assert review["requirement_id"] == str(req_id)

        # Assessment with comparison details.
        assert review["assessment"]["status"] == "compliant"
        assert review["assessment"]["suggested_status"] == "compliant"
        assert review["assessment"]["is_confirmed_by_human"] is False
        assert review["assessment"]["comparison_result"] is not None

        # Conflicts (CP56).
        assert len(review["conflicts"]) == 1
        assert review["conflicts"][0]["conflict_type"] == "parameter_value"
        assert review["conflicts"][0]["parameter"] == "temperature"
        assert review["conflicts"][0]["resolution"] == "unresolved"
        # All sources preserved.
        assert len(review["conflicts"][0]["sources"]) == 2

        # Clarifications (CP57).
        assert len(review["clarifications"]) == 1
        assert review["clarifications"][0]["context"]["parameter"] == "temperature"

        # Deviations (CP57).
        assert len(review["deviations"]) == 1
        assert review["deviations"][0]["deviation_type"] == "value"

    def test_review_no_assessment_returns_none(self, session_cm):
        """No assessment yet → review returns None."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                review = await svc.get_requirement_review(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                return review

        review = asyncio.run(_run())
        assert review is None


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestReviewTenantIsolation:
    """Cross-org access is denied for all review operations."""

    def test_cross_org_cannot_override(self, session_cm):
        _, org_a_id, proj_a_id = _setup_project_and_tenant(session_cm)
        req_id = _setup_requirement(session_cm, proj_a_id)
        _setup_evidence_and_vendor_spec(session_cm, proj_a_id, req_id)

        # Org B user.
        user_b_id = uuid.uuid4()
        org_b_id = uuid.uuid4()
        project_b_id = uuid.uuid4()

        async def _setup_org_b():
            async with session_cm() as session:
                session.add(Organization(id=org_b_id, name="Org B"))
                session.add(
                    User(
                        id=user_b_id,
                        auth_provider="dev",
                        auth_provider_user_id=str(user_b_id),
                    )
                )
                session.add(
                    Membership(
                        organization_id=org_b_id,
                        user_id=user_b_id,
                        role="owner",
                    )
                )
                session.add(
                    Project(
                        id=project_b_id,
                        organization_id=org_b_id,
                        name="Org B Project",
                        status=ProjectStatus.DRAFT,
                        created_by=user_b_id,
                    )
                )
                await session.commit()

        asyncio.run(_setup_org_b())
        auth_b = _make_auth(user_b_id, org_b_id)

        async def _run():
            async with session_cm() as session:
                svc = ComplianceAssessmentService(session)
                assessment = await svc.assess_requirement(
                    auth=_make_auth(uuid.uuid4(), org_a_id),
                    project_id=proj_a_id,
                    requirement_id=req_id,
                )
                assert assessment is not None
                # Org B tries to override org A's assessment.
                result = await svc.override_assessment(
                    auth=auth_b,
                    project_id=proj_a_id,
                    assessment_id=assessment.id,
                    status=ComplianceStatus.NON_COMPLIANT,
                    reason="Cross-org override attempt.",
                )
                return result

        result = asyncio.run(_run())
        assert result is None, "Cross-org override must be denied."
