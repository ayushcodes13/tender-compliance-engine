"""CP56 — Conflict and contradiction detection service.

This module provides the :class:`ConflictDetectionService` that scans all
accepted vendor evidence for a requirement and identifies contradictions
*without* silently discarding any source.  Every conflicting claim is
preserved in a persistent, auditable :class:`~tender_compliance_api.db.models.Conflict`
record.

Conflict types
--------------

* **parameter_value** — the same conceptual parameter appears in multiple
  accepted evidence items with different numeric values that are NOT
  unit-equivalent (e.g. one datasheet says 25 °C, another says 30 °C).
  Values that are dimensionally compatible AND numerically equal after
  conversion are NOT conflicts.
* **concept_mismatch** — different conceptual parameters that share a unit
  (e.g. accuracy vs resolution both expressed in mm).
* **tender_vendor** — the requirement text and an evidence/vendor-spec
  text directly contradict in language (e.g. "shall be CE marked" vs
  "not CE marked").

Design rules (do not violate)
-----------------------------

1.  **All sources preserved.**  Every conflicting evidence item and
    vendor spec is recorded in ``Conflict.sources``.  The system never
    picks the "preferred" value by priority, set-union, or arrival order.
2.  **No silent resolution.**  A detected conflict is ``UNRESOLVED`` until
    a human reviewer explicitly accepts or rejects it.
3.  **Numeric comparison uses the CP53 engine.**  Values are compared
    through :func:`~tender_compliance_api.extraction.spec_comparison._unit_adapter`
    so units and tolerances are handled deterministically.
4.  **Tenant isolation.**  Every query is scoped to ``auth.context``.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    Conflict,
    ConflictResolution,
    Evidence,
    EvidenceLocation,
    EvidenceReviewState,
    Project,
    Requirement,
    VendorSpec,
)
from tender_compliance_api.extraction.spec_comparison import _unit_adapter

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConflictSource:
    """A single source descriptor preserved inside a Conflict record."""

    evidence_id: str
    vendor_spec_id: str | None
    oem_document_version_id: str | None
    source_text: str
    value: float | None = None
    unit: str | None = None
    source_page_number: int | None = None
    condition: str | None = None

    def to_dict(self) -> dict[str, str | int | float | None]:
        return {
            "evidence_id": self.evidence_id,
            "vendor_spec_id": self.vendor_spec_id,
            "oem_document_version_id": self.oem_document_version_id,
            "source_text": self.source_text,
            "value": self.value,
            "unit": self.unit,
            "source_page_number": self.source_page_number,
            "condition": self.condition,
        }


@dataclass
class DetectedConflict:
    """A conflict found during detection, ready to be persisted."""

    conflict_type: str
    parameter: str | None
    entity: str | None
    sources: list[ConflictSource]
    tender_claim: str | None = None
    tender_vendor_spec_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Regexes for tender-vendor contradiction detection
# ---------------------------------------------------------------------------

# Keywords that indicate a positive affirmation of a certification/property.
_POSITIVE_AFFIRMATION = re.compile(
    r"shall\s+(?:be\s+|must\s+(?:be\s+)?)"
    r"(?:CE|UL|RoHS|FCC|ex\s+compliant|compliant|complies|"
    r"marked|approved|covered|rated)",
    re.IGNORECASE,
)

# Keywords that indicate a negation / denial.
_NEGATION = re.compile(
    r"\b(?:not|no|never|without)\s+(?:CE|UL|RoHS|FCC|compliant|complies|"
    r"certified|approved|marked|supported|covered|rated)\b",
    re.IGNORECASE,
)


class ConflictDetectionService:
    """Detect and persist contradictions between vendor evidence (CP56).

    All public methods are async and tenant-scoped through the supplied
    :class:`~tender_compliance_api.auth.context.AuthContext`.
    """

    def __init__(
        self,
        db: AsyncSession,
        audit: AuditService,
    ) -> None:
        self._db = db
        self._audit = audit

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def detect_conflicts(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> list[DetectedConflict]:
        """Run conflict detection for one requirement.

        Returns a list of detected conflicts (not yet persisted).  The caller
        may then choose to persist them via :meth:`record_conflicts`.
        """
        req = await self._fetch_requirement(auth, project_id, requirement_id)
        if req is None:
            raise ValueError(
                f"Requirement {requirement_id} not found in project "
                f"{project_id}"
            )

        evidence_items = await self._fetch_accepted_evidence(
            auth, project_id, requirement_id
        )

        all_vendor_specs: list[tuple[Evidence, VendorSpec]] = []
        all_sources: list[ConflictSource] = []

        for ev in evidence_items:
            # Fetch evidence locations for source_text / page number.
            loc_stmt = select(EvidenceLocation).where(
                EvidenceLocation.evidence_id == ev.id
            )
            locs: list[EvidenceLocation] = list(
                (await self._db.execute(loc_stmt)).scalars().all()
            )

            # Fetch vendor specs for this evidence.
            vs_stmt = select(VendorSpec).where(
                VendorSpec.evidence_id == ev.id
            )
            vendor_specs: list[VendorSpec] = list(
                (await self._db.execute(vs_stmt)).scalars().all()
            )

            for vs in vendor_specs:
                all_vendor_specs.append((ev, vs))
                source_text = (
                    vs.qualitative_statement
                    if vs.qualitative_statement
                    else (locs[0].source_text if locs else "")
                )
                source_desc = ConflictSource(
                    evidence_id=str(ev.id),
                    vendor_spec_id=str(vs.id),
                    oem_document_version_id=(
                        str(vs.oem_document_version_id)
                        if vs.oem_document_version_id
                        else None
                    ),
                    source_text=source_text or "",
                    value=(
                        float(vs.value)
                        if vs.value is not None
                        else None
                    ),
                    unit=vs.unit,
                    source_page_number=_first_page(locs),
                    condition=vs.parameter,
                )
                all_sources.append(source_desc)

        conflicts: list[DetectedConflict] = []

        # 1. Parameter value conflicts (numeric mismatch across evidence).
        param_conflicts = self._detect_parameter_value_conflicts(
            all_vendor_specs, all_sources
        )
        conflicts.extend(param_conflicts)

        # 2. Concept mismatch (accuracy vs resolution etc.).
        concept_conflicts = self._detect_concept_mismatches(
            all_sources, req
        )
        conflicts.extend(concept_conflicts)

        # 3. Tender-vendor contradiction.
        tv_conflicts = self._detect_tender_vendor_contradictions(
            req, all_sources
        )
        conflicts.extend(tv_conflicts)

        return conflicts

    async def record_conflicts(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        conflicts: list[DetectedConflict],
    ) -> list[Conflict]:
        """Persist detected conflicts as auditable records.

        Each conflict is stored with all its sources — none are discarded.
        If a conflict already exists for the same requirement+parameter+type,
        it is updated (new sources appended) rather than duplicated.
        """
        persisted: list[Conflict] = []
        for dc in conflicts:
            existing = await self._find_existing_conflict(
                auth, project_id, requirement_id, dc
            )
            if existing:
                # Append new sources to existing record (deduplicated).
                existing_sources = existing.sources
                new_dicts = [
                    s.to_dict()
                    for s in dc.sources
                    if s.to_dict() not in existing_sources
                ]
                if new_dicts:
                    existing_sources.extend(new_dicts)
                existing.updated_at = datetime.now(UTC)
                self._db.add(existing)
                persisted.append(existing)
            else:
                conflict = Conflict(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    requirement_id=requirement_id,
                    conflict_type=dc.conflict_type,
                    parameter=dc.parameter,
                    entity=dc.entity,
                    sources=[s.to_dict() for s in dc.sources],
                    tender_claim=dc.tender_claim,
                    tender_vendor_spec_id=dc.tender_vendor_spec_id,
                    resolution=ConflictResolution.UNRESOLVED,
                )
                self._db.add(conflict)
                persisted.append(conflict)

        await self._db.flush()
        for c in persisted:
            await self._audit.log(
                organization_id=auth.organization_id,
                actor_id=auth.actor_id,
                action="conflict_recorded",
                entity_type="conflict",
                entity_id=c.id,
                project_id=project_id,
                metadata={
                    "project_id": str(project_id),
                    "requirement_id": str(requirement_id),
                    "conflict_type": c.conflict_type,
                    "parameter": c.parameter,
                    "num_sources": len(c.sources),
                },
            )
        await self._db.commit()
        return persisted

    async def list_conflicts(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> list[Conflict]:
        """List all conflicts for a requirement (tenant-scoped)."""
        stmt = (
            select(Conflict)
            .join(Project)
            .where(
                Conflict.project_id == project_id,
                Project.organization_id == auth.organization_id,
                Conflict.requirement_id == requirement_id,
            )
            .order_by(Conflict.created_at)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_conflict(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        conflict_id: uuid.UUID,
    ) -> Conflict | None:
        """Fetch a single conflict by ID (tenant-scoped)."""
        return await self._fetch_conflict(auth, project_id, conflict_id)

    async def resolve_conflict(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        conflict_id: uuid.UUID,
        resolution: ConflictResolution,
        notes: str | None = None,
    ) -> Conflict | None:
        """Human resolution of a conflict (ACCEPTED or REJECTED).

        A human may ACCEPT (keep the conflicting evidence, acknowledge it)
        or REJECT (discard one vendor's claim).  UNRESOLVED is not a valid
        resolution action — it is the default state.

        Returns ``None`` if the conflict does not exist in the tenant
        scope (tenant isolation).
        """
        if resolution == ConflictResolution.UNRESOLVED:
            raise ValueError(
                "Cannot set resolution to UNRESOLVED via this method; "
                "the default state is already UNRESOLVED."
            )

        conflict = await self._fetch_conflict(auth, project_id, conflict_id)
        if conflict is None:
            return None

        conflict.resolution = resolution
        conflict.resolution_notes = notes
        conflict.resolved_by = auth.actor_id
        conflict.resolved_at = datetime.now(UTC)
        conflict.updated_at = datetime.now(UTC)
        self._db.add(conflict)

        await self._audit.log(
            organization_id=auth.organization_id,
            actor_id=auth.actor_id,
            action="conflict_resolved",
            entity_type="conflict",
            entity_id=conflict_id,
            project_id=project_id,
            metadata={
                "resolution": resolution.value,
                "notes": notes,
            },
        )
        await self._db.flush()
        await self._db.commit()
        return conflict

    async def detect_and_record(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> list[Conflict]:
        """Convenience: detect then persist in one call."""
        detected = await self.detect_conflicts(
            auth, project_id, requirement_id
        )
        if detected:
            return await self.record_conflicts(
                auth, project_id, requirement_id, detected
            )
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_requirement(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> Requirement | None:
        from tender_compliance_api.db.models import (
            DocumentVersion,
            TenderDocument,
        )

        stmt = (
            select(Requirement)
            .join(
                DocumentVersion,
                Requirement.document_version_id == DocumentVersion.id,
            )
            .join(
                TenderDocument,
                DocumentVersion.document_id == TenderDocument.id,
            )
            .join(Project, TenderDocument.project_id == Project.id)
            .where(
                Requirement.id == requirement_id,
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def _fetch_accepted_evidence(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> list[Evidence]:
        from tender_compliance_api.db.models import (
            DocumentVersion,
            TenderDocument,
        )

        stmt = (
            select(Evidence)
            .join(Requirement)
            .join(
                DocumentVersion,
                Requirement.document_version_id == DocumentVersion.id,
            )
            .join(
                TenderDocument,
                DocumentVersion.document_id == TenderDocument.id,
            )
            .join(Project, TenderDocument.project_id == Project.id)
            .where(
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
                Evidence.requirement_id == requirement_id,
                Evidence.review_state == EvidenceReviewState.ACCEPTED,
            )
            .order_by(Evidence.created_at)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_conflict(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        conflict_id: uuid.UUID,
    ) -> Conflict | None:
        stmt = (
            select(Conflict)
            .join(Project)
            .where(
                Conflict.id == conflict_id,
                Conflict.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def _find_existing_conflict(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        dc: DetectedConflict,
    ) -> Conflict | None:
        stmt = (
            select(Conflict)
            .join(Project)
            .where(
                Conflict.project_id == project_id,
                Project.organization_id == auth.organization_id,
                Conflict.requirement_id == requirement_id,
                Conflict.conflict_type == dc.conflict_type,
                Conflict.parameter == dc.parameter,
                Conflict.entity == dc.entity,
            )
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    def _detect_parameter_value_conflicts(
        self,
        vendor_specs: list[tuple[Evidence, VendorSpec]],
        sources: list[ConflictSource],
    ) -> list[DetectedConflict]:
        """Detect same parameter with non-equivalent numeric values across evidence.

        Uses the CP53 unit adapter to check whether two values for the same
        parameter are dimensionally compatible AND numerically equal after
        conversion.  Only if they are NOT equivalent do we flag a conflict.
        """
        # Group by parameter name (case-insensitive).
        by_param: dict[
            str, list[tuple[Evidence, VendorSpec, ConflictSource]]
        ] = {}
        for ev, vs in vendor_specs:
            if vs.parameter is None:
                continue
            param_key = vs.parameter.strip().lower()
            src = next(
                (s for s in sources if s.vendor_spec_id == str(vs.id)),
                ConflictSource(
                    evidence_id=str(ev.id),
                    vendor_spec_id=str(vs.id),
                    oem_document_version_id=None,
                    source_text="",
                ),
            )
            by_param.setdefault(param_key, []).append((ev, vs, src))

        conflicts: list[DetectedConflict] = []
        for _param, entries in by_param.items():
            if len(entries) < 2:
                continue

            # Collect distinct source descriptors.
            sources_for_conflict = [e[2] for e in entries]

            # Check whether values are truly different (not just unit variants).
            distinct_values = self._distinct_numeric_values(sources_for_conflict)
            if len(distinct_values) <= 1:
                continue

            entity = entries[0][1].entity if entries[0][1].entity else None
            conflicts.append(
                DetectedConflict(
                    conflict_type="parameter_value",
                    parameter=entries[0][1].parameter,
                    entity=entity,
                    sources=sources_for_conflict,
                )
            )
        return conflicts

    def _detect_concept_mismatches(
        self,
        sources: list[ConflictSource],
        req: Requirement,
    ) -> list[DetectedConflict]:
        """Detect conceptually different parameters conflated via same unit.

        For example, if one evidence item says "accuracy 0.5mm" and another
        says "resolution 0.5mm", the numbers are identical but the concepts
        differ.  The CP53 spec comparison engine treats these as
        INCOMPARABLE — we surface the same information as a concept_mismatch
        conflict.
        """
        req_text = req.raw_source or ""
        req_lower = req_text.lower()

        # Group sources by unit.
        by_unit: dict[str, list[ConflictSource]] = {}
        for s in sources:
            if s.unit is None or s.value is None:
                continue
            by_unit.setdefault(s.unit, []).append(s)

        conflicts: list[DetectedConflict] = []
        for _unit, unit_sources in by_unit.items():
            if len(unit_sources) < 2:
                continue
            # Check if the parameters (conditions) differ conceptually.
            params = {s.condition for s in unit_sources if s.condition}
            if len(params) > 1:
                # Different parameters with same unit — potential concept mismatch.
                # Only flag if the requirement text mentions one specific parameter.
                mentioned_params = [
                    p for p in params if p and p.lower() in req_lower
                ]
                if mentioned_params:
                    conflicts.append(
                        DetectedConflict(
                            conflict_type="concept_mismatch",
                            parameter=", ".join(sorted(params)),
                            entity=None,
                            sources=unit_sources,
                            tender_claim=req_text[:500],
                        )
                    )
        return conflicts

    def _detect_tender_vendor_contradictions(
        self,
        req: Requirement,
        sources: list[ConflictSource],
    ) -> list[DetectedConflict]:
        """Detect direct linguistic contradictions between tender and evidence."""
        req_text = req.raw_source or ""
        conflicts: list[DetectedConflict] = []

        req_has_positive = bool(_POSITIVE_AFFIRMATION.search(req_text))
        req_has_negation = bool(_NEGATION.search(req_text))

        for s in sources:
            if not s.source_text:
                continue
            ev_has_positive = bool(_POSITIVE_AFFIRMATION.search(s.source_text))
            ev_has_negation = bool(_NEGATION.search(s.source_text))

            # Tender says affirmative, evidence says negation.
            if req_has_positive and ev_has_negation:
                conflicts.append(
                    DetectedConflict(
                        conflict_type="tender_vendor",
                        parameter=s.condition,
                        entity=s.condition,
                        sources=[s],
                        tender_claim=req_text[:500],
                        tender_vendor_spec_id=(
                            uuid.UUID(s.vendor_spec_id)
                            if s.vendor_spec_id
                            else None
                        ),
                    )
                )

            # Tender says negation, evidence says affirmative.
            if req_has_negation and ev_has_positive:
                conflicts.append(
                    DetectedConflict(
                        conflict_type="tender_vendor",
                        parameter=s.condition,
                        entity=s.condition,
                        sources=[s],
                        tender_claim=req_text[:500],
                        tender_vendor_spec_id=(
                            uuid.UUID(s.vendor_spec_id)
                            if s.vendor_spec_id
                            else None
                        ),
                    )
                )

        return conflicts

    # ------------------------------------------------------------------
    # Numeric utilities using CP53 unit adapter
    # ------------------------------------------------------------------

    def _distinct_numeric_values(
        self, sources: list[ConflictSource]
    ) -> list[tuple[float, str | None]]:
        """Return list of distinct values after unit normalization.

        Two values are considered the same if they are dimensionally
        compatible AND numerically equal after conversion.  This prevents
        false conflicts like "25 °C" vs "77 °F" (which are equivalent).
        """
        canonical: list[tuple[float, str | None]] = []

        for s in sources:
            if s.value is None:
                continue
            value = s.value
            unit = s.unit
            is_duplicate = False
            for c_val, c_unit in canonical:
                if unit == c_unit:
                    if abs(value - c_val) < 1e-9:
                        is_duplicate = True
                        break
                elif (
                    unit is not None
                    and c_unit is not None
                    and _unit_adapter.compatible(unit, c_unit)
                ):
                    converted = _unit_adapter.convert(value, unit, c_unit)
                    if converted is not None and abs(converted - c_val) < 1e-9:
                        is_duplicate = True
                        break
            if not is_duplicate:
                canonical.append((value, unit))

        return canonical


def _first_page(locs: list[EvidenceLocation]) -> int | None:
    """Return the first available page number from locations."""
    for loc in locs:
        if loc.page_number is not None:
            return loc.page_number
    return None
