"""Tests for CP56 — Conflict and contradiction detection.

Covers:
- Parameter value conflict: same parameter, different numeric values across
  accepted evidence items.
- Unit equivalence: 25 °C vs 77 °F NOT flagged (unit-normalized via CP53 engine).
- Concept mismatch: accuracy vs resolution with same unit → flagged.
- Tender-vendor contradiction: "shall be CE marked" vs "not CE marked".
- All conflicting sources preserved (never silently discarded).
- Conflict persistence with dedup (re-detect → no duplicate).
- Human resolution ACCEPT/REJECT/UNRESOLVED-validation.
- Tenant isolation (cross-org denied).
- No fabrication: conflicts only from actual evidence.
- Evidence review_state filtering (only ACCEPTED evidence considered).
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.compliance.conflict_detection import (
    ConflictDetectionService,
    ConflictSource,
    DetectedConflict,
)
from tender_compliance_api.db.models import (
    Conflict,
    ConflictResolution,
    ConstraintNormalizationState,
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
    Requirement,
    TenderDocument,
    User,
    VendorSpec,
    VendorSpecExtractionMethod,
)

# ---------------------------------------------------------------------------
# Helpers — inlined to avoid cross-test-module imports
# ---------------------------------------------------------------------------


def _headers(user_id: uuid.UUID, org_id: uuid.UUID) -> dict[str, str]:
    return {
        "x-dev-user-id": str(user_id),
        "x-dev-organization-id": str(org_id),
    }


def _setup_project_and_tenant(
    session_cm,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create org, user, membership, project.  Returns (user_id, org_id, proj_id)."""

    async def _setup() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="CP56 Test Org"))
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
                    name="CP56 Project",
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
    raw_source: str = "The product shall operate from 5 V to 12 V DC.",
    normalized_text: str | None = None,
) -> uuid.UUID:
    """Create a TenderDocument → DocumentVersion → Requirement."""

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
                    promotion_key="req-cp56-1",
                    requirement_type="qualitative",
                    normalized_text=normalized_text or raw_source,
                    raw_source=raw_source,
                    uncertainty="exact",
                )
            )
            await session.commit()
        return req_id

    return asyncio.run(_setup())


def _setup_evidence_with_vendor_spec(
    session_cm,
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    *,
    evidence_text: str = "Operating temperature: -10 to 50 °C.",
    vendor_spec_param: str = "operating_temperature",
    vendor_spec_entity: str | None = None,
    vendor_value: float | None = None,
    vendor_unit: str | None = None,
    review_state: EvidenceReviewState = EvidenceReviewState.ACCEPTED,
    ocr_confidence: float | None = None,
) -> uuid.UUID:
    """Create OEM doc/version chain, text segment, evidence, and optional vendor spec.

    Returns the evidence_id.
    """

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

            # Always create a VendorSpec when parameter is provided.
            if vendor_spec_param is not None:
                session.add(
                    VendorSpec(
                        id=uuid.uuid4(),
                        evidence_id=evidence.id,
                        requirement_id=requirement_id,
                        oem_document_version_id=oem_version_id,
                        oem_text_segment_id=segment_id,
                        parameter=vendor_spec_param,
                        entity=vendor_spec_entity,
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


def _make_service(session_cm) -> ConflictDetectionService:
    async def _make() -> ConflictDetectionService:
        async with session_cm() as session:
            return ConflictDetectionService(
                db=session, audit=AuditService(session)
            )

    return asyncio.run(_make())


# ---------------------------------------------------------------------------
# Helper to run async service calls
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine and return the result."""
    return asyncio.run(coro)


async def _run_detect(
    session_cm,
    auth: AuthContext,
    project_id: uuid.UUID,
    req_id: uuid.UUID,
) -> list[DetectedConflict]:
    async with session_cm() as session:
        svc = ConflictDetectionService(
            db=session, audit=AuditService(session)
        )
        return await svc.detect_conflicts(
            auth=auth, project_id=project_id, requirement_id=req_id
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParameterValueConflict:
    """Same parameter, different numeric values → parameter_value conflict."""

    def test_different_values_same_parameter(self, session_cm):
        """Two evidence items with same parameter, different values."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 30 °C ambient temperature.",
        )
        # Evidence 1: 25 °C
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        # Evidence 2: 30 °C
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 30 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "parameter_value"
        assert conflicts[0].parameter == "ambient_temperature"
        # Both sources preserved.
        assert len(conflicts[0].sources) == 2
        values = {s.value for s in conflicts[0].sources}
        assert values == {25.0, 30.0}

    def test_unit_equivalent_not_conflict(self, session_cm):
        """25 °C vs 77 °F are numerically equivalent → NO conflict."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        # Evidence 1: 25 °C
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        # Evidence 2: 77 °F (= 25 °C)
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 77 °F.",
            vendor_spec_param="ambient_temperature",
            vendor_value=77.0,
            vendor_unit="degF",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))

        # Unit-equivalent values should NOT be flagged as conflict.
        param_conflicts = [
            c for c in conflicts
            if c.conflict_type == "parameter_value"
        ]
        assert len(param_conflicts) == 0, (
            "25°C and 77°F are mathematically equivalent and should not be "
            "flagged as a parameter_value conflict."
        )

    def test_single_evidence_no_conflict(self, session_cm):
        """Only one evidence item → no parameter_value conflict possible."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))
        assert len(conflicts) == 0

    def test_rejected_evidence_not_considered(self, session_cm):
        """REJECTED evidence items are not considered for conflict detection."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        # Evidence 1: ACCEPTED, 25 °C
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
            review_state=EvidenceReviewState.ACCEPTED,
        )
        # Evidence 2: REJECTED, 30 °C — should NOT trigger conflict
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 30 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
            review_state=EvidenceReviewState.REJECTED,
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))
        param_conflicts = [
            c for c in conflicts
            if c.conflict_type == "parameter_value"
        ]
        assert len(param_conflicts) == 0


class TestConceptMismatch:
    """Concept mismatch: accuracy vs resolution with same unit → flagged."""

    def test_accuracy_vs_resolution_same_unit(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The sensor accuracy shall be 0.1 mm.",
        )
        # Evidence 1: accuracy 0.1mm
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Accuracy: 0.1 mm.",
            vendor_spec_param="accuracy",
            vendor_value=0.1,
            vendor_unit="mm",
        )
        # Evidence 2: resolution 0.1mm (same unit, different concept)
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Resolution: 0.1 mm.",
            vendor_spec_param="resolution",
            vendor_value=0.1,
            vendor_unit="mm",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))
        concept_conflicts = [
            c for c in conflicts
            if c.conflict_type == "concept_mismatch"
        ]
        assert len(concept_conflicts) == 1
        assert "accuracy" in concept_conflicts[0].parameter
        assert "resolution" in concept_conflicts[0].parameter

    def test_concept_mismatch_not_flagged_if_req_doesnt_mention(self, session_cm):
        """If the requirement text doesn't mention either parameter, no concept mismatch."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall be IP65 rated.",
        )
        # Two evidence items with same-unit, different-concept params
        # (but requirement does not mention either).
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Accuracy: 0.1 mm.",
            vendor_spec_param="accuracy",
            vendor_value=0.1,
            vendor_unit="mm",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Resolution: 0.1 mm.",
            vendor_spec_param="resolution",
            vendor_value=0.1,
            vendor_unit="mm",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))
        concept_conflicts = [
            c for c in conflicts
            if c.conflict_type == "concept_mismatch"
        ]
        assert len(concept_conflicts) == 0


class TestTenderVendorContradiction:
    """Tender-vendor: 'shall be CE marked' vs 'not CE marked'."""

    def test_affirmation_vs_negation(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The product shall be CE marked.",
        )
        # Evidence: "not CE marked"
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="The product is not CE marked.",
            vendor_spec_param="certification",
            vendor_spec_entity="CE marking",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))
        tv_conflicts = [
            c for c in conflicts if c.conflict_type == "tender_vendor"
        ]
        assert len(tv_conflicts) == 1
        assert len(tv_conflicts[0].sources) == 1

    def test_no_contradiction_when_both_affirmative(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The product shall be CE marked.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="The product is CE marked.",
            vendor_spec_param="certification",
            vendor_spec_entity="CE marking",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))
        tv_conflicts = [
            c for c in conflicts if c.conflict_type == "tender_vendor"
        ]
        assert len(tv_conflicts) == 0


class TestConflictPersistence:
    """Persist conflicts and verify sources are preserved."""

    def test_record_and_retrieve(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 30 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        async def _run():
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                detected = await svc.detect_conflicts(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                persisted = await svc.record_conflicts(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                    conflicts=detected,
                )

                # Retrieve from DB.
                retrieved = await svc.list_conflicts(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                return persisted, retrieved

        persisted, retrieved = asyncio.run(_run())
        assert len(persisted) == 1
        assert len(retrieved) == 1
        # All sources preserved.
        assert len(retrieved[0].sources) == 2
        assert retrieved[0].resolution == ConflictResolution.UNRESOLVED.value

    def test_redetect_no_duplicate(self, session_cm):
        """Re-detecting the same conflict should not create a duplicate."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 30 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        async def _run():
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                # First detect + record.
                detected1 = await svc.detect_conflicts(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                await svc.record_conflicts(
                    auth=auth, project_id=proj_id,
                    requirement_id=req_id, conflicts=detected1
                )
                # Second detect + record.
                detected2 = await svc.detect_conflicts(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                await svc.record_conflicts(
                    auth=auth, project_id=proj_id,
                    requirement_id=req_id, conflicts=detected2
                )
                return await svc.list_conflicts(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )

        retrieved = asyncio.run(_run())
        assert len(retrieved) == 1, (
            "Re-detecting the same conflict should update, not duplicate."
        )


class TestConflictResolution:
    """Human resolution of conflicts."""

    def test_accept_conflict(self, session_cm):
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 30 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        async def _run():
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                detected = await svc.detect_conflicts(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                persisted = await svc.record_conflicts(
                    auth=auth, project_id=proj_id,
                    requirement_id=req_id, conflicts=detected
                )
                conflict_id = persisted[0].id

                resolved = await svc.resolve_conflict(
                    auth=auth,
                    project_id=proj_id,
                    conflict_id=conflict_id,
                    resolution=ConflictResolution.ACCEPTED,
                    notes="Accepted discrepancy — both temperatures valid "
                          "for different operating modes.",
                )
                return resolved

        resolved = asyncio.run(_run())
        assert resolved.resolution == ConflictResolution.ACCEPTED
        assert resolved.resolved_by == user_id
        assert resolved.resolved_at is not None
        assert resolved.resolution_notes.startswith("Accepted")

    def test_unresolved_rejected(self, session_cm):
        """Setting UNRESOLVED via resolve_conflict must raise."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 30 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        async def _run():
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                detected = await svc.detect_conflicts(
                    auth=auth, project_id=proj_id, requirement_id=req_id
                )
                persisted = await svc.record_conflicts(
                    auth=auth, project_id=proj_id,
                    requirement_id=req_id, conflicts=detected
                )
                conflict_id = persisted[0].id

                # Trying to resolve as UNRESOLVED should raise ValueError.
                try:
                    await svc.resolve_conflict(
                        auth=auth,
                        project_id=proj_id,
                        conflict_id=conflict_id,
                        resolution=ConflictResolution.UNRESOLVED,
                    )
                    return "no_error"
                except ValueError:
                    return "value_error"

        result = asyncio.run(_run())
        assert result == "value_error"


class TestTenantIsolation:
    """Cross-organization access denied."""

    def test_cross_org_cannot_detect(self, session_cm):
        """User from org B cannot detect conflicts in org A's project."""
        user_a_id, org_a_id, proj_a_id = _setup_project_and_tenant(
            session_cm
        )
        # User and org B (different from A).
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

        # Set up a conflict in org A's project.
        req_id = _setup_requirement(
            session_cm, proj_a_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_a_id, req_id,
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_a_id, req_id,
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        # Org B user tries to detect conflicts in org A's project.
        auth_b = _make_auth(org_b_id)
        # detect_conflicts raises ValueError when the requirement is
        # not visible to this tenant (tenant isolation).
        try:
            conflicts = _run_async(
                _run_detect(session_cm, auth_b, proj_a_id, req_id)
            )
        except ValueError:
            conflicts = []
        assert len(conflicts) == 0, (
            "Cross-org access must be denied — no conflicts visible."
        )

    def test_cross_org_cannot_persist(self, session_cm):
        """User from org B cannot resolve org A's conflicts."""
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

        # Set up a conflict in org A's project.
        req_id = _setup_requirement(
            session_cm, proj_a_id,
            raw_source="The device shall operate at 25 °C.",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_a_id, req_id,
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        _setup_evidence_with_vendor_spec(
            session_cm, proj_a_id, req_id,
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        # Org A creates a conflict.
        auth_a = _make_auth(org_a_id)

        async def _setup_conflict():
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                detected = await svc.detect_conflicts(
                    auth=auth_a, project_id=proj_a_id, requirement_id=req_id
                )
                persisted = await svc.record_conflicts(
                    auth=auth_a,
                    project_id=proj_a_id,
                    requirement_id=req_id,
                    conflicts=detected,
                )
                return persisted[0].id

        conflict_id = asyncio.run(_setup_conflict())

        # Org B user tries to resolve the conflict in org A's project.
        auth_b = _make_user_auth(
            uuid.uuid4(), org_b_id
        )  # user_b has owner role in org B

        async def _try_resolve():
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                result = await svc.resolve_conflict(
                    auth=auth_b,
                    project_id=proj_a_id,
                    conflict_id=conflict_id,
                    resolution=ConflictResolution.ACCEPTED,
                )
                return result

        # Should not find the conflict (tenant-isolated query returns None).
        result = asyncio.run(_try_resolve())
        assert result is None, (
            "Cross-org conflict resolution must be denied (returns None)."
        )


class TestNoFabrication:
    """Conflicts only from actual evidence — never fabricated."""

    def test_no_evidence_no_conflict(self, session_cm):
        """Requirement with no accepted evidence → no conflicts."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )

        conflicts = _run_async(_run_detect(session_cm, auth, proj_id, req_id))
        assert len(conflicts) == 0

    def test_sources_are_real_evidence_ids(self, session_cm):
        """Every source.evidence_id in a conflict must be a real evidence UUID."""
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_auth(org_id)
        req_id = _setup_requirement(
            session_cm, proj_id,
            raw_source="The device shall operate at 25 °C.",
        )
        ev1_id = _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )
        ev2_id = _setup_evidence_with_vendor_spec(
            session_cm, proj_id, req_id,
            evidence_text="Ambient temperature: 30 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=30.0,
            vendor_unit="degC",
        )

        async def _run_and_verify():
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                conflicts = await svc.detect_conflicts(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                )
                # Collect all evidence IDs from the DB.
                ev_stmt = select(Evidence.id).where(
                    Evidence.requirement_id == req_id
                )
                ev_ids = {
                    str(r) for r in (await session.execute(ev_stmt)).scalars().all()
                }
                # Check every source's evidence_id is in the DB.
                for c in conflicts:
                    for s in c.sources:
                        assert s.evidence_id in ev_ids, (
                            f"Source evidence_id {s.evidence_id} is not a "
                            f"real evidence UUID — fabrication detected."
                        )
                # Verify both evidence IDs are represented.
                source_ev_ids = {
                    s.evidence_id for c in conflicts
                    for s in c.sources
                }
                assert str(ev1_id) in source_ev_ids
                assert str(ev2_id) in source_ev_ids
                return conflicts

        asyncio.run(_run_and_verify())


# ---------------------------------------------------------------------------
# Regression: record_conflicts must commit Conflict rows so the conflicts
# endpoint (persist=true) survives across requests — without an in-service
# commit the route returns rows but the DB stays empty.
# ---------------------------------------------------------------------------


class TestConflictPersistenceAcrossSessions:
    def test_record_conflicts_persists_for_subsequent_session(self, session_cm) -> None:
        user_id, org_id, proj_id = _setup_project_and_tenant(session_cm)
        auth = _make_user_auth(user_id, org_id)
        req_id = _setup_requirement(session_cm, proj_id)
        evidence_id = _setup_evidence_with_vendor_spec(
            session_cm,
            proj_id,
            req_id,
            evidence_text="Ambient temperature: 25 °C.",
            vendor_spec_param="ambient_temperature",
            vendor_value=25.0,
            vendor_unit="degC",
        )

        detected = DetectedConflict(
            conflict_type="parameter_value",
            parameter="ambient_temperature",
            entity=None,
            sources=[
                ConflictSource(
                    evidence_id=str(evidence_id),
                    vendor_spec_id=None,
                    oem_document_version_id=None,
                    source_text="Ambient temperature: 25 °C.",
                    value=25.0,
                    unit="degC",
                )
            ],
            tender_claim="shall operate at 30 °C",
        )

        async def _run() -> list:
            async with session_cm() as session:
                svc = ConflictDetectionService(
                    db=session, audit=AuditService(session)
                )
                return await svc.record_conflicts(
                    auth=auth,
                    project_id=proj_id,
                    requirement_id=req_id,
                    conflicts=[detected],
                )

        persisted = asyncio.run(_run())
        assert len(persisted) == 1

        async def _count() -> int:
            async with session_cm() as s:
                rows = (
                    await s.execute(
                        select(Conflict).where(Conflict.requirement_id == req_id)
                    )
                ).scalars().all()
                return len(rows)

        count = asyncio.run(_count())
        assert count == 1, f"conflict not persisted across sessions (got {count})"
