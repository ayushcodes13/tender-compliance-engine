"""Tests for CP57 — Missing evidence, clarification questions, and deviations.

Covers:
- Create clarification request (PENDING)
- Auto-generate: missing evidence → clarification request
- Auto-generate: unresolved conflict → clarification request
- Auto-generate: UNCERTAIN qualitative assessment → clarification request
- Answer clarification request (ANSWERED)
- Cannot re-answer an already answered clarification
- List clarifications with filters
- Tenant isolation (cross-org denied)
- Create deviation (PROPOSED)
- Review deviation (ACCEPTED / REJECTED)
- Cannot set deviation to PROPOSED via review
- Cannot change already-reviewed deviation
- List deviations with filters
- No fabrication: question text is verbatim
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.compliance.missing_evidence import (
    ClarificationContext,
    MissingEvidenceService,
)
from tender_compliance_api.db.models import (
    ClarificationStatus,
    Conflict,
    ConflictResolution,
    ConstraintNormalizationState,
    DeviationStatus,
    DeviationType,
    DocumentProcessingStatus,
    DocumentVersion,
    Evidence,
    EvidenceLocation,
    EvidenceReviewState,
    Membership,
    OemDocument,
    OemDocumentType,
    OemDocumentVersion,
    OemTextSegment,
    Organization,
    Project,
    ProjectStatus,
    QualitativeAssessment,
    QualitativeVerdict,
    Requirement,
    TenderDocument,
    User,
    VendorSpec,
    VendorSpecExtractionMethod,
)

# ---------------------------------------------------------------------------
# Helpers
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
            session.add(Organization(id=org_id, name="CP57 Test Org"))
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
                    name="CP57 Project",
                    status=ProjectStatus.DRAFT,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


def _make_auth(org_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        actor_id=uuid.uuid4(),
        organization_id=org_id,
        roles={"owner"},
    )


def _make_user_auth(user_id: uuid.UUID, org_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        actor_id=user_id,
        organization_id=org_id,
        roles={"owner"},
    )


def _setup_requirement(
    session_cm,
    project_id: uuid.UUID,
    raw_source: str = "The product shall be CE marked.",
    normalized_text: str | None = None,
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
                    promotion_key="req-cp57-1",
                    requirement_type="qualitative",
                    normalized_text=normalized_text or raw_source,
                    raw_source=raw_source,
                    uncertainty="exact",
                )
            )
            await session.commit()
        return req_id

    return asyncio.run(_setup())


def _setup_evidence(
    session_cm,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    *,
    evidence_text: str = "The product is CE marked.",
    review_state: EvidenceReviewState = EvidenceReviewState.ACCEPTED,
    ocr_confidence: float | None = None,
    vendor_spec_param: str | None = "certification",
    vendor_value: float | None = None,
    vendor_unit: str | None = None,
    entity: str | None = None,
) -> uuid.UUID:
    """Create OEM doc/version chain, text segment, accepted evidence + vendor spec."""

    async def _setup() -> uuid.UUID:
        oem_doc_id = uuid.uuid4()
        oem_version_id = uuid.uuid4()
        evidence_id = uuid.uuid4()
        segment_id = uuid.uuid4()

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
            segment = OemTextSegment(
                id=segment_id,
                oem_document_version_id=oem_version_id,
                page_number=1,
                segment_index=0,
                start_char=0,
                end_char=len(evidence_text),
                text=evidence_text,
                ocr_confidence=ocr_confidence,
            )
            session.add(segment)
            await session.flush()

            evidence = Evidence(
                id=evidence_id,
                requirement_id=requirement_id,
                oem_document_version_id=oem_version_id,
                review_state=review_state,
                score=0.9,
            )
            session.add(evidence)
            await session.flush()

            session.add(
                EvidenceLocation(
                    evidence_id=evidence.id,
                    oem_text_segment_id=segment_id,
                    oem_document_version_id=oem_version_id,
                    page_number=1,
                    char_start=0,
                    char_end=len(evidence_text),
                    location_type=(
                        "approximate"
                        if ocr_confidence is not None
                        else "exact"
                    ),
                    source_text=evidence_text,
                    ocr_confidence=ocr_confidence,
                )
            )

            if vendor_spec_param is not None:
                session.add(
                    VendorSpec(
                        id=uuid.uuid4(),
                        evidence_id=evidence.id,
                        requirement_id=requirement_id,
                        oem_document_version_id=oem_version_id,
                        oem_text_segment_id=segment_id,
                        parameter=vendor_spec_param,
                        entity=entity,
                        value=vendor_value,
                        unit=vendor_unit,
                        source_text=evidence_text,
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
    sources: list[dict[str, Any]] | None = None,
) -> uuid.UUID:
    """Create a Conflict record directly (for auto-generation test)."""

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
                    sources=sources or [],
                    tender_claim="test claim",
                    resolution=ConflictResolution.UNRESOLVED,
                )
            )
            await session.commit()
        return conflict_id

    return asyncio.run(_setup())


def _setup_qualitative_uncertain(
    session_cm,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
) -> None:
    """Create a QualitativeAssessment with UNCERTAIN verdict."""

    async def _setup():
        async with session_cm() as session:
            session.add(
                QualitativeAssessment(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    requirement_id=requirement_id,
                    verdict=QualitativeVerdict.UNCERTAIN,
                    reason_code="ocr_warning",
                    reason_text="Uncertain due to OCR",
                    evidence_ids=[],
                    attribution_mismatches=[],
                    source_contradiction=False,
                    model_version="test-v1",
                    prompt_version="test-v1",
                    reasoning_version="test-v1",
                    assessment_version=1,
                    is_confirmed_by_human=False,
                )
            )
            await session.commit()

    asyncio.run(_setup())


# ---------------------------------------------------------------------------
# Tests — Clarifications
# ---------------------------------------------------------------------------


class TestClarificationRequests:
    """Create, answer, list clarification requests."""

    def test_create_clarification(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Is the product CE marked?",
                    context=ClarificationContext(
                        reason="missing_evidence",
                        parameter="certification",
                        detail="No evidence found.",
                    ),
                    requirement_id=req_id,
                )
                return cr

        cr = asyncio.run(_run())
        assert cr.question == "Is the product CE marked?"
        assert cr.status == ClarificationStatus.PENDING
        assert cr.context["reason"] == "missing_evidence"
        assert cr.asked_by == user_id

    def test_answer_clarification(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Is the product CE marked?",
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                answered = await svc.answer_clarification(
                    auth=auth,
                    project_id=proj_id,
                    clarification_id=cr.id,
                    answer="Yes, the product is CE marked per EN 60950.",
                )
                return cr, answered

        cr, answered = asyncio.run(_run())
        assert answered.status == ClarificationStatus.ANSWERED
        assert answered.answer == "Yes, the product is CE marked per EN 60950."
        assert answered.answered_by == user_id
        assert answered.answered_at is not None
        # updated_at must be set on answer for audit/versioning.
        assert answered.updated_at is not None

    def test_edit_clarification_question(self, session_cm):
        """A human can edit an auto-generated clarification question verbatim."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Original auto-generated question?",
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                edited = await svc.edit_clarification(
                    auth=auth,
                    project_id=proj_id,
                    clarification_id=cr.id,
                    question="Refined question from human reviewer.",
                )
                return cr, edited

        cr, edited = asyncio.run(_run())
        assert edited is not None
        assert edited.question == "Refined question from human reviewer."
        assert edited.updated_at is not None and edited.updated_at >= cr.asked_at

    def test_edit_clarification_context(self, session_cm):
        """Editing only the context leaves the question untouched."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Q?",
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                edited = await svc.edit_clarification(
                    auth=auth,
                    project_id=proj_id,
                    clarification_id=cr.id,
                    context={"reason": "missing_evidence", "parameter": "voltage"},
                )
                return cr, edited

        cr, edited = asyncio.run(_run())
        assert edited is not None
        assert edited.question == cr.question  # unchanged
        assert edited.context["parameter"] == "voltage"

    def test_cannot_edit_answered_clarification(self, session_cm):
        """ANSWERED clarifications are locked for editing."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Q?",
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                await svc.answer_clarification(
                    auth=auth,
                    project_id=proj_id,
                    clarification_id=cr.id,
                    answer="A.",
                )
                try:
                    await svc.edit_clarification(
                        auth=auth,
                        project_id=proj_id,
                        clarification_id=cr.id,
                        question="Edited after answer?",
                    )
                    return "no_error"
                except ValueError:
                    return "value_error"

        result = asyncio.run(_run())
        assert result == "value_error"

    def test_cannot_reanswer(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Q?",
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                await svc.answer_clarification(
                    auth=auth,
                    project_id=proj_id,
                    clarification_id=cr.id,
                    answer="A.",
                )
                try:
                    await svc.answer_clarification(
                        auth=auth,
                        project_id=proj_id,
                        clarification_id=cr.id,
                        answer="B.",
                    )
                    return "no_error"
                except ValueError:
                    return "value_error"

        result = asyncio.run(_run())
        assert result == "value_error"

    def test_list_clarifications(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Q1?",
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question="Q2?",
                    context=ClarificationContext(reason="conflict"),
                    requirement_id=req_id,
                )
                all_crs = await svc.list_clarifications(
                    auth=auth, project_id=proj_id
                )
                pending = await svc.list_clarifications(
                    auth=auth,
                    project_id=proj_id,
                    status=ClarificationStatus.PENDING,
                )
                return all_crs, pending

        all_crs, pending = asyncio.run(_run())
        assert len(all_crs) == 2
        assert len(pending) == 2


class TestAutoGenerate:
    """Auto-generate clarification requests for missing evidence, conflicts, OCR."""

    def test_missing_evidence_generates_clarification(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The product shall be CE marked.",
        )
        # No evidence created — should trigger missing_evidence.

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                created = await svc.auto_generate_clarifications(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                return created

        created = asyncio.run(_run())
        assert len(created) >= 1
        missing_ev = [
            c for c in created
            if c.context.get("reason") == "missing_evidence"
        ]
        assert len(missing_ev) == 1
        assert "No accepted evidence" in missing_ev[0].question

    def test_conflict_generates_clarification(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temp: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        _setup_conflict(
            session_cm, proj_id, req_id,
            conflict_type="parameter_value",
            parameter="ambient_temperature",
            sources=[
                {"evidence_id": str(uuid.uuid4()), "source_text": "25 °C"},
                {"evidence_id": str(uuid.uuid4()), "source_text": "30 °C"},
            ],
        )

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                created = await svc.auto_generate_clarifications(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                return created

        created = asyncio.run(_run())
        conflict_crs = [
            c for c in created
            if c.context.get("reason") == "conflict"
        ]
        assert len(conflict_crs) == 1
        assert conflict_crs[0].related_conflict_ids is not None
        assert len(conflict_crs[0].related_conflict_ids) == 1

    def test_uncertain_assessment_generates_clarification(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The product shall be CE marked.",
        )
        _setup_evidence(
            session_cm, proj_id, req_id,
            evidence_text="The product is CE marked.",
            vendor_spec_param="certification",
        )
        _setup_qualitative_uncertain(session_cm, proj_id, req_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                created = await svc.auto_generate_clarifications(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                return created

        created = asyncio.run(_run())
        uncertain_crs = [
            c for c in created
            if c.context.get("reason") == "ambiguous_requirement"
        ]
        assert len(uncertain_crs) == 1


class TestDeviations:
    """Create and review deviations."""

    def test_create_deviation(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                dev = await svc.create_deviation(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                    deviation_type=DeviationType.VALUE,
                    original_requirement="Shall operate at 25 °C.",
                    proposed_alternative="Propose 30 °C instead.",
                    rationale="Component availability.",
                )
                return dev

        dev = asyncio.run(_run())
        assert dev.deviation_type == DeviationType.VALUE
        assert dev.status == DeviationStatus.PROPOSED
        assert dev.original_requirement == "Shall operate at 25 °C."
        assert dev.proposed_alternative == "Propose 30 °C instead."
        assert dev.proposed_by == user_id

    def test_accept_deviation(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                dev = await svc.create_deviation(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                    deviation_type=DeviationType.SCOPE,
                    original_requirement="Shall support 100 users.",
                    proposed_alternative="Support 50 users.",
                )
                reviewed = await svc.review_deviation(
                    auth=auth,
                    project_id=proj_id,
                    deviation_id=dev.id,
                    status=DeviationStatus.ACCEPTED,
                    review_notes="Scope reduction approved.",
                )
                return reviewed

        reviewed = asyncio.run(_run())
        assert reviewed.status == DeviationStatus.ACCEPTED
        assert reviewed.reviewed_by == user_id
        assert reviewed.review_notes == "Scope reduction approved."

    def test_proposed_status_rejected(self, session_cm):
        """Setting PROPOSED via review must raise ValueError."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                dev = await svc.create_deviation(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                    deviation_type=DeviationType.OTHER,
                    original_requirement="Req.",
                )
                try:
                    await svc.review_deviation(
                        auth=auth,
                        project_id=proj_id,
                        deviation_id=dev.id,
                        status=DeviationStatus.PROPOSED,
                    )
                    return "no_error"
                except ValueError:
                    return "value_error"

        result = asyncio.run(_run())
        assert result == "value_error"

    def test_cannot_change_reviewed_deviation(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                dev = await svc.create_deviation(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                    deviation_type=DeviationType.VALUE,
                    original_requirement="Req.",
                )
                await svc.review_deviation(
                    auth=auth,
                    project_id=proj_id,
                    deviation_id=dev.id,
                    status=DeviationStatus.REJECTED,
                )
                try:
                    await svc.review_deviation(
                        auth=auth,
                        project_id=proj_id,
                        deviation_id=dev.id,
                        status=DeviationStatus.ACCEPTED,
                    )
                    return "no_error"
                except ValueError:
                    return "value_error"

        result = asyncio.run(_run())
        assert result == "value_error"

    def test_list_deviations(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req1 = _setup_requirement(session_cm, proj_id, raw_source="Req 1.")
        req2 = _setup_requirement(session_cm, proj_id, raw_source="Req 2.")

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                dev1 = await svc.create_deviation(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req1,
                    deviation_type=DeviationType.VALUE,
                    original_requirement="Req 1.",
                )
                _ = await svc.create_deviation(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req2,
                    deviation_type=DeviationType.SCOPE,
                    original_requirement="Req 2.",
                )
                await svc.review_deviation(
                    auth=auth,
                    project_id=proj_id,
                    deviation_id=dev1.id,
                    status=DeviationStatus.ACCEPTED,
                )
                all_devs = await svc.list_deviations(
                    auth=auth, project_id=proj_id
                )
                accepted = await svc.list_deviations(
                    auth=auth,
                    project_id=proj_id,
                    status=DeviationStatus.ACCEPTED,
                )
                proposed = await svc.list_deviations(
                    auth=auth,
                    project_id=proj_id,
                    status=DeviationStatus.PROPOSED,
                )
                return all_devs, accepted, proposed

        all_devs, accepted, proposed = asyncio.run(_run())
        assert len(all_devs) == 2
        assert len(accepted) == 1
        assert len(proposed) == 1


class TestTenantIsolationCP57:
    """Cross-organization access denied for clarifications and deviations."""

    def test_cross_org_cannot_create_clarification(self, session_cm):
        """User from org B cannot create clarifications in org A's project."""
        _, org_a_id, proj_a_id = _setup_project_and_tenant(session_cm)
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

        auth_b = _make_user_auth(user_b_id, org_b_id)
        req_id = _setup_requirement(
            session_cm, proj_a_id,
            raw_source="The product shall be CE marked.",
        )

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                try:
                    await svc.create_clarification(
                        auth=auth_b,
                        project_id=proj_a_id,
                        question="Q?",
                        context=ClarificationContext(reason="missing_evidence"),
                        requirement_id=req_id,
                    )
                    return "no_error"
                except ValueError:
                    return "denied"

        result = asyncio.run(_run())
        assert result == "denied", (
            "Cross-org clarification creation must be denied."
        )

    def test_cross_org_cannot_edit_clarification(self, session_cm):
        """User from org B cannot edit org A's clarification request."""
        user_a_id, org_a_id, proj_a_id = _setup_project_and_tenant(
            session_cm
        )
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

        auth_a = _make_user_auth(user_a_id, org_a_id)
        auth_b = _make_user_auth(user_b_id, org_b_id)
        req_id = _setup_requirement(
            session_cm, proj_a_id,
            raw_source="The product shall be CE marked.",
        )

        async def _create():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth_a,
                    project_id=proj_a_id,
                    question="Q?",
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                return cr.id

        cr_id = asyncio.run(_create())

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                edited = await svc.edit_clarification(
                    auth=auth_b,
                    project_id=proj_a_id,
                    clarification_id=cr_id,
                    question="Edited by org B.",
                )
                return edited

        edited = asyncio.run(_run())
        assert edited is None, (
            "Cross-org clarification edit must return None (denied)."
        )


class TestNoFabricationCP57:
    """Question text and deviation fields are verbatim — never synthesized."""

    def test_clarification_question_preserved(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)

        question = "Does the device meet IP65 ingress protection per IEC 60529?"

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                cr = await svc.create_clarification(
                    auth=auth,
                    project_id=proj_id,
                    question=question,
                    context=ClarificationContext(reason="missing_evidence"),
                    requirement_id=req_id,
                )
                return cr

        cr = asyncio.run(_run())
        assert cr.question == question

    def test_deviation_original_preserved(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="Shall operate from -20 °C to +60 °C.",
        )

        async def _run():
            async with session_cm() as session:
                svc = MissingEvidenceService(
                    db=session, audit=AuditService(session)
                )
                dev = await svc.create_deviation(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                    deviation_type=DeviationType.VALUE,
                    original_requirement="Shall operate from -20 °C to +60 °C.",
                    proposed_alternative="Propose -10 °C to +50 °C.",
                )
                return dev

        dev = asyncio.run(_run())
        assert dev.original_requirement == "Shall operate from -20 °C to +60 °C."
        assert dev.proposed_alternative == "Propose -10 °C to +50 °C."
