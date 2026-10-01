"""Tests for CP34 — Qualitative normalization and ambiguity escalation.

Service-layer integration tests verifying that ``normalize_requirement_constraints``
persists parsed constraints (numeric + qualitative) into RequirementConstraint rows,
propagates OCR warnings to the requirement's review_state, and is idempotent.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from tender_compliance_api.db.models import (
    ConstraintNormalizationState,
    DocumentProcessingStatus,
    DocumentVersion,
    Membership,
    Organization,
    Project,
    ProjectStatus,
    Requirement,
    RequirementConstraint,
    RequirementReviewState,
    TenderDocument,
    User,
)
from tender_compliance_api.document import DocumentService

# ---------------------------------------------------------------------------
# Helpers (mirror test_document_processing.py patterns)
# ---------------------------------------------------------------------------

def _mk_auth(org_id: uuid.UUID, user_id: uuid.UUID):
    from types import SimpleNamespace
    return SimpleNamespace(organization_id=org_id, actor_id=user_id)


def _build_org_project(session_cm):
    """Set up org + user + membership + project; return (user_id, org_id, project_id)."""
    async def _setup():
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        async with session_cm() as session:
            session.add(Organization(id=org_id, name="CP34 Test Org"))
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
                    name="CP34 Project",
                    status=ProjectStatus.TENDER_UPLOADED,
                    created_by=user_id,
                )
            )
            await session.commit()
        return user_id, org_id, project_id

    return asyncio.run(_setup())


def _create_doc_version_and_requirement(
    session_cm, project_id: uuid.UUID, raw_source: str, ocr_warning: bool = False
) -> uuid.UUID:
    """Create a document version + requirement; return requirement_id."""
    async def _create():
        async with session_cm() as session:
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
                promotion_key="pk-test-" + str(uuid.uuid4())[:8],
                requirement_type="obligation",
                normalized_text=raw_source,
                raw_source=raw_source,
                uncertainty="confirmed",
                ocr_warning=ocr_warning,
                review_state=RequirementReviewState.UNREVIEWED,
            )
            session.add(req)
            await session.commit()
            return req.id

    return asyncio.run(_create())


# ---------------------------------------------------------------------------
# Service integration: persist constraints
# ---------------------------------------------------------------------------

class TestNormalizeRequirementConstraints:
    """Verify normalize_requirement_constraints persists constraints and
    propagates uncertainty to review_state."""

    def test_numeric_constraints_persisted(self, session_cm) -> None:
        """Numeric constraints parsed from raw_source are persisted as rows."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, "weight ≤ 2 kg"
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                # We need the document_id and version_number — fetch them.
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                parsed = await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )
                assert len(parsed) == 1
                assert parsed[0].operator == "<="
                assert parsed[0].numeric_value == 2.0
                assert parsed[0].unit == "kg"

                # Verify persistence
                constraints = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                assert len(constraints) == 1
                assert constraints[0].operator == "<="
                assert constraints[0].numeric_value == 2.0
                assert constraints[0].unit == "kg"
                assert (
                    constraints[0].normalization_state
                    is ConstraintNormalizationState.SAFE
                )
                assert constraints[0].raw_fragment == "weight ≤ 2 kg"

        asyncio.run(_run())

    def test_qualitative_constraints_persisted(self, session_cm) -> None:
        """Qualitative conditions are persisted alongside numeric ones."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id,
            "IP65 enclosure, weight ≤ 2 kg, stainless steel housing."
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )

                constraints = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                # 1 numeric (weight ≤ 2 kg) + qualitative (IP65, stainless steel)
                assert len(constraints) >= 2
                params = {c.parameter for c in constraints}
                assert "mass" in params
                assert "environmental_rating" in params
                assert "material" in params

                # Qualitative condition should have the condition text
                qual = [c for c in constraints if c.qualitative_condition]
                assert len(qual) >= 2

        asyncio.run(_run())

    def test_ocr_warning_escalates_review_state(self, session_cm) -> None:
        """When the requirement has ocr_warning=True, review_state
        escalates to OCR_WARNING."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, "weight ≤ 2 kg", ocr_warning=True
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )

                req = (
                    await session.execute(
                        select(Requirement).where(Requirement.id == req_id)
                    )
                ).scalar_one()
                assert req.review_state is RequirementReviewState.OCR_WARNING

                # All constraints should be PARTIAL (ocr_warning escalation)
                constraints = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                assert all(
                    c.normalization_state is ConstraintNormalizationState.PARTIAL
                    for c in constraints
                )

        asyncio.run(_run())

    def test_corrupted_number_constraint_partially(self, session_cm) -> None:
        """When a constraint has an unknown unit (e.g. "2O" split as num=2 +
        unit='O'), the normalization state is PARTIAL and the requirement
        stays UNREVIEWED (no ocr_warning flag on the requirement itself).
        The constraint is still persisted for human review, never silently
        promoted to SAFE."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, "weight ≤ 2O kg"
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )

                req = (
                    await session.execute(
                        select(Requirement).where(Requirement.id == req_id)
                    )
                ).scalar_one()
                # No ocr_warning on the requirement → stays UNREVIEWED.
                assert req.review_state is RequirementReviewState.UNREVIEWED

                constraints = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                # The constraint is persisted with PARTIAL state (unknown_unit).
                assert len(constraints) == 1
                assert (
                    constraints[0].normalization_state
                    is ConstraintNormalizationState.PARTIAL
                )

        asyncio.run(_run())

    def test_idempotent_reprocess(self, session_cm) -> None:
        """Re-running normalization replaces, not duplicates, constraints."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, "weight ≤ 2 kg and IP65 enclosure."
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                # First run
                await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )
                count1 = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                n1 = len(count1)

                # Second run — should replace, not add
                await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )
                count2 = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                n2 = len(count2)

                assert n1 == n2, (
                    f"Idempotency failed: {n1} constraints before, {n2} after"
                )
                assert n1 >= 2  # at least mass + environmental_rating

        asyncio.run(_run())

    def test_tenant_isolation(self, session_cm) -> None:
        """A user from a different organization cannot normalize constraints
        for a requirement in another org's project."""
        from tender_compliance_api.document import DocumentNotFoundError

        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, "weight ≤ 2 kg"
        )

        # Fetch the doc_id with the legitimate org's auth.
        async def _get_doc_id():
            async with session_cm() as session:
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                return version.document_id

        doc_id = asyncio.run(_get_doc_id())

        # Create a second org/user that is NOT a member of the project.
        async def _setup_other():
            other_org = uuid.uuid4()
            other_user = uuid.uuid4()
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
                        organization_id=other_org, user_id=other_user, role="owner"
                    )
                )
                await session.commit()
            return other_user, other_org

        other_user, other_org = asyncio.run(_setup_other())

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(other_org, other_user)
                with pytest.raises(DocumentNotFoundError):
                    await svc.normalize_requirement_constraints(
                        auth, doc_id, 1, req_id
                    )

        asyncio.run(_run())

    def test_empty_raw_source_yields_no_constraints(self, session_cm) -> None:
        """A requirement with empty raw_source produces no constraints."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, ""
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                parsed = await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )
                assert parsed == []

                constraints = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                assert len(constraints) == 0

        asyncio.run(_run())

    def test_normalized_text_updated(self, session_cm) -> None:
        """The requirement's normalized_text is set to the conservative
        whitespace-normalized raw_source."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        raw = "The  equipment   shall  operate  at  a maximum  noise  level  of 70 dB."
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, raw
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )

                req = (
                    await session.execute(
                        select(Requirement).where(Requirement.id == req_id)
                    )
                ).scalar_one()
                # Whitespace should be collapsed but content preserved.
                assert "  " not in req.normalized_text
                assert "70 dB" in req.normalized_text

        asyncio.run(_run())

    def test_no_numeric_no_qualitative_yields_unnormalized(self, session_cm) -> None:
        """A requirement with only vague prose (no conditions extracted)
        leaves normalization_state as UNNORMALIZED."""
        user_id, org_id, project_id = _build_org_project(session_cm)
        req_id = _create_doc_version_and_requirement(
            session_cm, project_id, "As required by applicable standards."
        )

        async def _run():
            async with session_cm() as session:
                svc = DocumentService(session)
                auth = _mk_auth(org_id, user_id)
                result = await session.execute(
                    select(DocumentVersion).join(TenderDocument).where(
                        TenderDocument.project_id == project_id
                    )
                )
                version = result.scalar_one()
                doc_id = version.document_id

                parsed = await svc.normalize_requirement_constraints(
                    auth, doc_id, 1, req_id
                )
                assert parsed == []

                constraints = (
                    await session.execute(
                        select(RequirementConstraint).where(
                            RequirementConstraint.requirement_id == req_id
                        )
                    )
                ).scalars().all()
                assert len(constraints) == 0

        asyncio.run(_run())
