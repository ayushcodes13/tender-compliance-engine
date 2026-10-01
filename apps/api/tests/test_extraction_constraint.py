"""Tests for CP32 — RequirementConstraint model + normalization states.

Model-only (schema/state) tests — CP33/CP34 own the deterministic parsing that
populates the parsed fields and transitions `normalization_state`. These tests
verify the schema, default state, raw-fragment preservation, multi-constraint
grouping, and a DB round-trip (via the session fixture + a persisted Requirement).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.db.models import (
    ConstraintNormalizationState,
    Requirement,
    RequirementConstraint,
    RequirementReviewState,
)

# ---------------------------------------------------------------------------
# 1. Normalization states are the closed, Phase-1 set.
# ---------------------------------------------------------------------------

def test_normalization_states_are_phase1_only() -> None:
    assert set(ConstraintNormalizationState) == {
        ConstraintNormalizationState.UNNORMALIZED,
        ConstraintNormalizationState.SAFE,
        ConstraintNormalizationState.PARTIAL,
        ConstraintNormalizationState.NEEDS_REVIEW,
    }
    # String values are stable / serialized.
    assert ConstraintNormalizationState.UNNORMALIZED.value == "unnormalized"
    assert ConstraintNormalizationState.SAFE.value == "safe"


def test_default_normalization_state_is_unnormalized() -> None:
    """The default normalization state is configured at the column level."""

    col = RequirementConstraint.__table__.c.normalization_state
    # Both a Python-side default (flush-time) and a DB-side server_default
    # (so a row inserted elsewhere still defaults to unormalized).
    assert col.default is not None
    assert col.server_default is not None
    assert "unnormalized" in str(col.server_default.arg)
    # Parsed fields are nullable — a guessed value is never required just to
    # satisfy the schema.
    for name in (
        "numeric_value",
        "lower_bound",
        "upper_bound",
        "tolerance",
    ):
        assert RequirementConstraint.__table__.c[name].nullable is True
    for name in ("operator", "unit", "qualitative_condition"):
        assert RequirementConstraint.__table__.c[name].nullable is True


# ---------------------------------------------------------------------------
# 2. Schema accepts the full field set (no guessed defaults).
# ---------------------------------------------------------------------------

def test_constraint_carries_all_parsed_fields() -> None:
    c = RequirementConstraint(
        requirement_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        parameter="operating_temperature",
        operator="<=",
        numeric_value=None,
        lower_bound=-10.0,
        upper_bound=55.0,
        unit="°C",
        tolerance=2.0,
        qualitative_condition="continuous full-load operation",
        normalization_state=ConstraintNormalizationState.SAFE,
        raw_fragment="operating temperature from -10 °C to +55 °C",
    )
    assert c.operator == "<="
    assert c.lower_bound == -10.0
    assert c.upper_bound == 55.0
    assert c.unit == "°C"
    assert c.tolerance == 2.0
    assert c.qualitative_condition == "continuous full-load operation"
    assert c.normalization_state is ConstraintNormalizationState.SAFE
    # raw fragment preserved verbatim
    assert c.raw_fragment == "operating temperature from -10 °C to +55 °C"


def test_multiple_constraints_per_requirement_via_relationship() -> None:
    req = Requirement(
        document_version_id=uuid.uuid4(),
        promotion_key="pk",
        requirement_type="obligation",
        normalized_text="weight + temp limit",
        raw_source="weight + temp limit",
        uncertainty="confirmed",
        review_state=RequirementReviewState.UNREVIEWED,
    )
    weight = RequirementConstraint(
        requirement_id=req.id,
        document_version_id=req.document_version_id,
        parameter="weight",
        operator="<",
        numeric_value=2.0,
        unit="kg",
        normalization_state=ConstraintNormalizationState.SAFE,
        raw_fragment="weigh less than 2 kg",
    )
    temp = RequirementConstraint(
        requirement_id=req.id,
        document_version_id=req.document_version_id,
        parameter="temperature",
        operator="between",
        lower_bound=-10.0,
        upper_bound=55.0,
        unit="°C",
        normalization_state=ConstraintNormalizationState.PARTIAL,
        raw_fragment="from -10 °C to +55 °C",
    )
    req.constraints = [weight, temp]
    assert len(req.constraints) == 2
    assert {c.parameter for c in req.constraints} == {"weight", "temperature"}


# ---------------------------------------------------------------------------
# 3. DB round-trip: persists + reads back verbatim, defaults applied.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("state", list(ConstraintNormalizationState))
def test_constraint_db_roundtrip(state: ConstraintNormalizationState) -> None:
    """Each normalization state round-trips through SQLite (server_default)."""

    async def _run() -> None:
        sf = _get_session_factory()
        version_id = uuid.uuid4()
        req_id = uuid.uuid4()
        async with sf() as session:
            _add_constraint_test_version(session, version_id)
            req = Requirement(
                id=req_id,
                document_version_id=version_id,
                promotion_key="pk-roundtrip",
                requirement_type="obligation",
                normalized_text="raw fragment here",
                raw_source="raw fragment here",
                uncertainty="confirmed",
                review_state=RequirementReviewState.UNREVIEWED,
            )
            session.add(req)
            session.add(
                RequirementConstraint(
                    requirement_id=req_id,
                    document_version_id=version_id,
                    parameter="weight",
                    operator="<",
                    numeric_value=2.0,
                    unit="kg",
                    tolerance=0.1,
                    normalization_state=state,
                    raw_fragment="weigh less than 2 kg ± 0.1",
                )
            )
            await session.commit()

        async with sf() as session:
            row = (
                await session.execute(
                    select(RequirementConstraint).where(
                        RequirementConstraint.requirement_id == req_id
                    )
                )
            ).scalar_one()
            assert row.document_version_id == version_id
            assert row.parameter == "weight"
            assert row.operator == "<"
            assert float(row.numeric_value) == 2.0
            assert row.unit == "kg"
            assert float(row.tolerance) == 0.1
            assert row.normalization_state is state
            assert row.raw_fragment == "weigh less than 2 kg ± 0.1"
            assert row.requirement_id == req_id
            # the parent requirement exists (no lazy async load in sync context)
            parent = (
                await session.execute(
                    select(Requirement).where(Requirement.id == req_id)
                )
            ).scalar_one()
            assert parent.id == req_id

    asyncio.run(_run())


def test_default_state_applied_on_insert_without_explicit_state() -> None:
    """Omitting normalization_state at insert still yields UNNORMALIZED
    (server_default), so CP33/CP34 transitions from the right baseline."""

    async def _run() -> None:
        sf = _get_session_factory()
        version_id = uuid.uuid4()
        req_id = uuid.uuid4()
        async with sf() as session:
            _add_constraint_test_version(session, version_id)
            session.add(
                Requirement(
                    id=req_id,
                    document_version_id=version_id,
                    promotion_key="pk-default",
                    requirement_type="obligation",
                    normalized_text="raw fragment here",
                    raw_source="raw fragment here",
                    uncertainty="confirmed",
                    review_state=RequirementReviewState.UNREVIEWED,
                )
            )
            session.add(
                RequirementConstraint(
                    requirement_id=req_id,
                    document_version_id=version_id,
                    parameter="weight",
                    raw_fragment="weigh less than 2 kg",
                )
            )
            await session.commit()

        async with sf() as session:
            row = (
                await session.execute(
                    select(RequirementConstraint).where(
                        RequirementConstraint.requirement_id == req_id
                    )
                )
            ).scalar_one()
            assert (
                row.normalization_state is ConstraintNormalizationState.UNNORMALIZED
            )
            assert row.numeric_value is None

    asyncio.run(_run())


def _add_constraint_test_version(session: AsyncSession, version_id: uuid.UUID) -> None:
    """Minimal tenant/project/doc/version scaffold (self-contained)."""

    from tender_compliance_api.db.models import (
        DocumentProcessingStatus,
        DocumentVersion,
        Membership,
        Organization,
        Project,
        StoredObject,
        TenderDocument,
        User,
    )
    from tender_compliance_api.storage.keys import build_key

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    stored_id = uuid.uuid4()
    key = build_key(
        org_id=org_id, project_id=project_id, document_id=doc_id, version=1
    )
    session.add_all(
        [
            Organization(id=org_id, name="CP32 Org"),
            User(
                id=user_id,
                auth_provider="dev",
                auth_provider_user_id=str(user_id),
            ),
            Membership(organization_id=org_id, user_id=user_id, role="owner"),
            Project(id=project_id, organization_id=org_id, name="CP32 Project"),
            StoredObject(
                id=stored_id,
                organization_id=org_id,
                project_id=project_id,
                storage_key=key,
                filename="tender.pdf",
                content_type="application/pdf",
                content_length=10,
                checksum_sha256="abc123",
            ),
            TenderDocument(id=doc_id, project_id=project_id, display_name="t.pdf"),
            DocumentVersion(
                id=version_id,
                document_id=doc_id,
                version_number=1,
                stored_object_id=stored_id,
                sha256="abc123",
                mime_type="application/pdf",
                size_bytes=10,
                processing_status=DocumentProcessingStatus.QUEUED,
            ),
        ]
    )


def _get_session_factory():
    from tender_compliance_api.db.session import _session_factory

    assert _session_factory is not None
    return _session_factory
