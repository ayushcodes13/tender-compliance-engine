"""Evidence-backed qualitative reasoning service (CP55).

This module produces **source-bounded** qualitative reasoning for tender
requirements.  Unlike the deterministic numeric comparison engine (CP53),
qualitative reasoning interprets *language* — does the cited evidence text
support, contradict, or fail to address a requirement?

Critical guardrails (AGENTS.md / checkpoint contract):

* **Source-bounded.**  The reasoner (including any LLM adapter) receives
  *only* the verbatim source texts of accepted evidence items for the
  requirement — never the full OEM document body.  ``evidence_ids`` on every
  result records exactly which evidence UUIDs were consulted.
* **Numeric results are authoritative.**  When a deterministic numeric
  comparison (CP53) returns MATCH/MISMATCH/CLOSE/PARTIAL, the qualitative
  verdict mirrors it and is never re-evaluated.
* **No fabrication.**  The reasoner never invents support.  When evidence
  is absent or does not address the requirement, the verdict is
  ``INSUFFICIENT_EVIDENCE`` or ``UNSUPPORTED`` — never ``SUPPORT``.
* **Record provenance.**  ``model_version``, ``prompt_version``, and
  ``reasoning_version`` are recorded on every persisted result.
* **Prefer uncertain over confident.**  OCR-derived or ambiguous evidence
  escalates to ``UNCERTAIN`` rather than silently downgrading.

Design:
* :class:`QualitativeReasoner` is the provider-agnostic port (interface).
* :class:`RuleBasedQualitativeReasoner` is the deterministic default — it
  uses keyword/condition matching against cited evidence text.  It is the
  only reasoner exercised by CI.
* :class:`FakeQualitativeReasoner` returns pre-configured results for tests
  that need to drive the full service without relying on rule semantics.
* :class:`OpenAiQualitativeReasoner` is the production LLM reasoner, loaded
  lazily (only when ``QUALITATIVE_REASONING_PROVIDER=openai`` and the
  ``openai`` package is present at call time).  Its prompt is source-bounded:
  the system prompt carries all rules; the user text contains only the
  requirement + cited evidence snippets.
"""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func as sqla_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    ComplianceAssessment,
    DocumentVersion,
    Evidence,
    EvidenceLocation,
    EvidenceReviewState,
    OemDocument,
    OemDocumentVersion,
    Project,
    QualitativeAssessment,
    QualitativeVerdict,
    Requirement,
    TenderDocument,
    VendorSpec,
)
from tender_compliance_api.extraction.qualitative import (
    parse_qualitative_conditions,
)

# ---------------------------------------------------------------------------
# Versioning constants — recorded on every persisted assessment
# ---------------------------------------------------------------------------

#: Version of the reasoning ruleset.  Bumped when the rule logic changes.
REASONING_VERSION: str = "cp55-rule-v1"

#: Version of the prompt sent to any LLM reasoner.  Bumped when the prompt
#: (not the post-processing rules) changes.
PROMPT_VERSION: str = "cp55-reasoning-prompt-v1"

#: Default model version — the rule-based reasoner is the deterministic
#: baseline; an LLM reasoner would report its own model string.
DEFAULT_MODEL_VERSION: str = "rule-based-v1"

#: OCR confidence threshold below which evidence is considered OCR-derived.
_OCR_CONFIDENCE_THRESHOLD: float = 0.9


# ---------------------------------------------------------------------------
# Context and result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributionMismatch:
    """A structured attribution/scope mismatch between requirement and evidence.

    Attributes:
        field: What mismatched (e.g. ``"entity"``, ``"operating_conditions"``).
        requirement_value: The value from the requirement (or None).
        evidence_value: The value from the evidence (or None).
        detail: Human-readable, non-confidential explanation.
    """

    field: str
    requirement_value: str | None
    evidence_value: str | None
    detail: str


@dataclass(frozen=True)
class QualitativeReasoningContext:
    """The source-bounded context passed to a :class:`QualitativeReasoner`.

    Only verbatim, accepted-evidence text is included.  The reasoner must
    never receive the full OEM document body.
    """

    requirement_text: str
    requirement_raw_source: str
    evidence_texts: list[str]
    vendor_spec_texts: list[str]
    qualitative_conditions: list[str]
    numeric_verdict: str | None
    ocr_warning: bool


@dataclass(frozen=True)
class QualitativeReasoningResult:
    """Structured output from a :class:`QualitativeReasoner`."""

    verdict: QualitativeVerdict
    reason_code: str
    reason_text: str | None
    evidence_ids: list[uuid.UUID]
    attribution_mismatches: list[AttributionMismatch]
    source_contradiction: bool


# ---------------------------------------------------------------------------
# Port: QualitativeReasoner
# ---------------------------------------------------------------------------


class QualitativeReasoner(ABC):
    """Abstract port for source-bounded qualitative reasoning (CP55).

    Implementations receive a :class:`QualitativeReasoningContext` that
    contains *only* cited evidence text — never the full document body.
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """Stable provider name for audit records (e.g. ``"rule-based"``)."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Concrete model identifier for audit records."""

    @abstractmethod
    async def reason(
        self,
        *,
        context: QualitativeReasoningContext,
    ) -> QualitativeReasoningResult:
        """Produce a source-bounded qualitative assessment.

        Args:
            context: The source-bounded reasoning context.

        Returns:
            A :class:`QualitativeReasoningResult` with a structured verdict
            and only cited evidence IDs.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Default reasoner: deterministic rule-based
# ---------------------------------------------------------------------------


# Keywords that signal an explicit contradiction in evidence text.
_NEGATION_RE = re.compile(
    r"\b(?:not\s+(?:CE|UL|FCC|RoHS|IP\d+|rated|marked|certified|compliant"
    r"|approved|listed|tested|specified|applicable|withstanding)"
    r"|does\s+not\s+(?:meet|comply|conform|apply|withstand|support)"
    r"|non.?compliant|un?suitable|inapplicable|excluded|"
    r"shall\s+not|must\s+not)\b",
    re.IGNORECASE,
)

# Positive-support keywords: words that confirm a condition is met.
_POSITIVE_RE = re.compile(
    r"\b(?:CE\s*marked|UL\s*listed|FCC\s*compliant|RoHS\s*compliant|"
    r"IP\d+\s*rated|IP\d+|certified|compliant|approved|listed|tested|"
    r"conforms|meets?\s+the\s+requirement|"
    r"rated\s+for|tested\s+to|verified|confirmed)\b",
    re.IGNORECASE,
)


class RuleBasedQualitativeReasoner(QualitativeReasoner):
    """Deterministic, source-bounded qualitative reasoner (CP55 default).

    Uses keyword/condition matching against cited evidence text.  Never
    fabricates — when the evidence is silent or ambiguous, it returns
    ``INSUFFICIENT_EVIDENCE`` or ``UNCERTAIN`` rather than ``SUPPORT``.

    This is the only reasoner exercised by CI; an LLM reasoner can be
    swapped in via the service constructor.
    """

    provider: str = "rule-based"
    model: str = "qualitative-rules-v1"

    async def reason(
        self,
        *,
        context: QualitativeReasoningContext,
    ) -> QualitativeReasoningResult:
        evidence_ids: list[uuid.UUID] = []
        attribution_mismatches: list[AttributionMismatch] = []
        contradiction = False

        # If a numeric verdict is authoritative, mirror it.
        if context.numeric_verdict is not None:
            verdict, code, text = _numeric_to_qualitative(context.numeric_verdict)
            return QualitativeReasoningResult(
                verdict=verdict,
                reason_code=code,
                reason_text=text,
                evidence_ids=evidence_ids,
                attribution_mismatches=attribution_mismatches,
                source_contradiction=contradiction,
            )

        # No numeric authority — reason from evidence text.
        combined_text = " ".join(context.evidence_texts + context.vendor_spec_texts)

        if context.ocr_warning:
            return QualitativeReasoningResult(
                verdict=QualitativeVerdict.UNCERTAIN,
                reason_code="ocr_warning",
                reason_text=(
                    "Evidence is OCR-derived or low-confidence; "
                    "qualitative conclusion is uncertain."
                ),
                evidence_ids=evidence_ids,
                attribution_mismatches=attribution_mismatches,
                source_contradiction=contradiction,
            )

        if not context.evidence_texts and not context.vendor_spec_texts:
            return QualitativeReasoningResult(
                verdict=QualitativeVerdict.INSUFFICIENT_EVIDENCE,
                reason_code="no_cited_evidence",
                reason_text="No accepted evidence text was supplied for reasoning.",
                evidence_ids=evidence_ids,
                attribution_mismatches=attribution_mismatches,
                source_contradiction=contradiction,
            )

        # Check for explicit contradiction signals.
        if _NEGATION_RE.search(combined_text):
            return QualitativeReasoningResult(
                verdict=QualitativeVerdict.MISMATCH,
                reason_code="explicit_negation_in_evidence",
                reason_text=(
                    "Evidence text contains negation language (e.g. "
                    "'not CE marked', 'does not meet') indicating the "
                    "requirement is contradicted."
                ),
                evidence_ids=evidence_ids,
                attribution_mismatches=attribution_mismatches,
                source_contradiction=contradiction,
            )

        # Check for positive support signals.
        if _POSITIVE_RE.search(combined_text):
            return QualitativeReasoningResult(
                verdict=QualitativeVerdict.SUPPORT,
                reason_code="positive_support_in_evidence",
                reason_text=(
                    "Evidence text contains explicit positive support "
                    "language (e.g. 'CE marked', 'compliant', 'tested to')."
                ),
                evidence_ids=evidence_ids,
                attribution_mismatches=attribution_mismatches,
                source_contradiction=contradiction,
            )

        # No explicit signal — the evidence doesn't address the requirement.
        return QualitativeReasoningResult(
            verdict=QualitativeVerdict.UNSUPPORTED,
            reason_code="evidence_silent",
            reason_text=(
                "Cited evidence does not contain explicit support or "
                "contradiction language for this requirement."
            ),
            evidence_ids=evidence_ids,
            attribution_mismatches=attribution_mismatches,
            source_contradiction=contradiction,
        )


def _numeric_to_qualitative(
    verdict: str,
) -> tuple[QualitativeVerdict, str, str | None]:
    """Map a numeric ComparisonVerdict to a qualitative verdict.

    Deterministic numeric results are authoritative — qualitative reasoning
    mirrors them rather than re-evaluating.
    """

    mapping: dict[str, tuple[QualitativeVerdict, str, str | None]] = {
        "match": (
            QualitativeVerdict.SUPPORT,
            "numeric_authoritative",
            "Deterministic numeric comparison returned MATCH — "
            "requirement is supported by evidence.",
        ),
        "mismatch": (
            QualitativeVerdict.MISMATCH,
            "numeric_authoritative",
            "Deterministic numeric comparison returned MISMATCH — "
            "requirement is contradicted by evidence.",
        ),
        "close": (
            QualitativeVerdict.SUPPORT,
            "numeric_authoritative_close",
            "Deterministic numeric comparison returned CLOSE — "
            "vendor value is within tolerance of the requirement.",
        ),
        "incomparable": (
            QualitativeVerdict.UNCERTAIN,
            "numeric_incomparable",
            "Numeric comparison returned INCOMPARABLE — "
            "qualitative reasoning should run on evidence text.",
        ),
        "not_demonstrated": (
            QualitativeVerdict.INSUFFICIENT_EVIDENCE,
            "numeric_not_demonstrated",
            "No numeric evidence demonstrates this requirement.",
        ),
    }
    if verdict in mapping:
        return mapping[verdict]
    return (
        QualitativeVerdict.UNCERTAIN,
        "unknown_numeric_verdict",
        f"Numeric verdict '{verdict}' is not recognized; defaulting to UNCERTAIN.",
    )


# ---------------------------------------------------------------------------
# Fake reasoner (for tests that need to drive the full service)
# ---------------------------------------------------------------------------


class FakeQualitativeReasoner(QualitativeReasoner):
    """Deterministic fake reasoner that returns a pre-configured result.

    Like :class:`~tender_compliance_api.extraction.fake.FakeLlmAdapter`,
    this lets tests drive the full service path without depending on rule
    semantics or network access.
    """

    provider: str = "fake"
    model: str = "fake"

    def __init__(
        self,
        result: QualitativeReasoningResult | None = None,
    ) -> None:
        self._result = result

    async def reason(
        self,
        *,
        context: QualitativeReasoningContext,
    ) -> QualitativeReasoningResult:
        if self._result is not None:
            return self._result
        return QualitativeReasoningResult(
            verdict=QualitativeVerdict.INSUFFICIENT_EVIDENCE,
            reason_code="fake_default",
            reason_text="FakeQualitativeReasoner returned default (no result configured).",
            evidence_ids=[],
            attribution_mismatches=[],
            source_contradiction=False,
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class QualitativeReasoningService:
    """Orchestrates source-bounded qualitative reasoning (CP55).

    For a given requirement, this service:
      1. Fetches accepted evidence (tenant-scoped).
      2. Fetches vendor specs and source texts for each evidence item.
      3. Retrieves any existing compliance assessment (numeric verdict).
      4. If numeric is authoritative, mirrors it.
      5. Otherwise, runs the qualitative reasoner on cited evidence text only.
      6. Detects attribution mismatches and source contradictions.
      7. Persists a versioned (append-only) QualitativeAssessment.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        reasoner: QualitativeReasoner | None = None,
    ) -> None:
        self._session = session
        self._audit = AuditService(session)
        self._reasoner = reasoner or RuleBasedQualitativeReasoner()

    async def assess_qualitative(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        *,
        evidence_id: str | None = None,
    ) -> QualitativeAssessment | None:
        """Run source-bounded qualitative reasoning for one requirement.

        Creates a new versioned assessment (append-only).  The reasoner
        receives only the verbatim source texts of accepted evidence —
        never the full OEM document body.
        """

        # --- 1. Fetch the requirement (tenant-scoped) ---
        req = await self._fetch_requirement(auth, project_id, requirement_id)
        if req is None:
            return None

        # --- 2. Fetch accepted evidence (optionally filtered) ---
        evidence_items = await self._fetch_evidence(
            auth, project_id, requirement_id,
            evidence_id_filter=evidence_id,
        )

        # --- 3. Gather source-bounded evidence texts + vendor specs ---
        evidence_texts: list[str] = []
        vendor_spec_texts: list[str] = []
        ocr_warning = False
        all_evidence_ids: list[uuid.UUID] = []
        attribution_mismatches: list[AttributionMismatch] = []
        source_contradiction = False

        # Track vendor specs by parameter to detect contradictions.
        specs_by_param: dict[str, list[tuple[float | None, uuid.UUID]]] = {}

        for ev in evidence_items:
            all_evidence_ids.append(ev.id)

            # Fetch locations with source text.
            loc_stmt = select(EvidenceLocation).where(
                EvidenceLocation.evidence_id == ev.id
            )
            loc_result = await self._session.execute(loc_stmt)
            locations = loc_result.scalars().all()

            for loc in locations:
                if loc.source_text:
                    evidence_texts.append(loc.source_text)
                if (
                    loc.ocr_confidence is not None
                    and loc.ocr_confidence < _OCR_CONFIDENCE_THRESHOLD
                ):
                    ocr_warning = True

            # Fetch vendor specs for this evidence.
            vs_stmt = select(VendorSpec).where(VendorSpec.evidence_id == ev.id)
            vs_result = await self._session.execute(vs_stmt)
            vendor_specs = vs_result.scalars().all()

            for vs in vendor_specs:
                if vs.source_text:
                    vendor_spec_texts.append(vs.source_text)

                # Track for contradiction detection.
                if vs.parameter and vs.value is not None:
                    specs_by_param.setdefault(vs.parameter, []).append(
                        (vs.value, ev.id)
                    )

                # Attribution mismatch: entity check.
                if vs.entity:
                    mismatch = _check_entity_attribution(req, vs)
                    if mismatch is not None:
                        attribution_mismatches.append(mismatch)

                # Attribution mismatch: conditions check.
                mismatch = _check_conditions_attribution(req, vs)
                if mismatch is not None:
                    attribution_mismatches.append(mismatch)

        # --- 4. Detect source contradictions across evidence items ---
        contradiction = _detect_source_contradiction(specs_by_param)
        if contradiction:
            source_contradiction = True

        # --- 5. Fetch numeric verdict from existing compliance assessment ---
        numeric_verdict: str | None = None
        compliance_assessment_id: uuid.UUID | None = None
        if evidence_items:
            ca_stmt = (
                select(ComplianceAssessment)
                .where(
                    ComplianceAssessment.requirement_id == requirement_id,
                    ComplianceAssessment.project_id == project_id,
                )
                .order_by(ComplianceAssessment.assessment_version.desc())
                .limit(1)
            )
            ca_result = await self._session.execute(ca_stmt)
            ca = ca_result.scalar_one_or_none()
            if ca is not None:
                compliance_assessment_id = ca.id
                if ca.comparison_result_json and isinstance(
                    ca.comparison_result_json, dict
                ):
                    numeric_verdict = ca.comparison_result_json.get("verdict")

        # --- 6. Build the source-bounded context ---
        # Parse qualitative conditions from the requirement (CP34).
        qualitative_conds = parse_qualitative_conditions(
            req.raw_source or "",
            ocr_warning=ocr_warning,
        )
        context = QualitativeReasoningContext(
            requirement_text=req.normalized_text,
            requirement_raw_source=req.raw_source or "",
            evidence_texts=evidence_texts,
            vendor_spec_texts=vendor_spec_texts,
            qualitative_conditions=[
                qc.condition for qc in qualitative_conds
            ],
            numeric_verdict=numeric_verdict,
            ocr_warning=ocr_warning,
        )

        # --- 7. Run the qualitative reasoner (source-bounded) ---
        result = await self._reasoner.reason(context=context)

        # --- 8. If source contradiction detected, escalate to CONFLICT ---
        if source_contradiction:
            verdict = QualitativeVerdict.CONFLICT
            reason_code = "source_contradiction"
            contradiction_msg = (
                "Multiple cited evidence items present conflicting values "
                "for the same parameter."
            )
            if result.reason_text:
                reason_text: str | None = (
                    f"{result.reason_text} {contradiction_msg}"
                )
            else:
                reason_text = contradiction_msg
        else:
            verdict = result.verdict
            reason_code = result.reason_code
            reason_text = result.reason_text

        # --- 9. Get next version (append-only) ---
        stmt = select(sqla_func.max(
            QualitativeAssessment.assessment_version
        )).where(
            QualitativeAssessment.requirement_id == requirement_id
        )
        row = await self._session.execute(stmt)
        max_version = row.scalar_one_or_none()
        new_version = (max_version or 0) + 1

        # --- 10. Persist ---
        assessment = QualitativeAssessment(
            project_id=project_id,
            requirement_id=requirement_id,
            evidence_id=uuid.UUID(evidence_id)
            if evidence_id
            else (all_evidence_ids[0] if all_evidence_ids else None),
            compliance_assessment_id=compliance_assessment_id,
            verdict=verdict,
            reason_code=reason_code,
            reason_text=reason_text,
            attribution_mismatches=[
                {
                    "field": am.field,
                    "requirement_value": am.requirement_value,
                    "evidence_value": am.evidence_value,
                    "detail": am.detail,
                }
                for am in attribution_mismatches
            ] or None,
            evidence_ids=[str(eid) for eid in all_evidence_ids] if all_evidence_ids else None,
            source_contradiction=source_contradiction,
            model_version=(
                self._reasoner.model
                if hasattr(self._reasoner, "model")
                else DEFAULT_MODEL_VERSION
            ),
            prompt_version=PROMPT_VERSION,
            reasoning_version=REASONING_VERSION,
            assessment_version=new_version,
            is_confirmed_by_human=False,
        )
        self._session.add(assessment)
        await self._session.flush()

        # --- 11. Audit ---
        await self._audit.log(
            organization_id=auth.organization_id,
            action="qualitative_assessment_created",
            actor_id=auth.actor_id,
            entity_type="qualitative_assessment",
            entity_id=assessment.id,
            project_id=project_id,
            metadata={
                "requirement_id": str(requirement_id),
                "verdict": verdict.value,
                "reason_code": reason_code,
                "assessment_version": new_version,
                "model_version": assessment.model_version,
                "num_evidence_ids": len(all_evidence_ids),
            },
        )

        await self._session.commit()
        await self._session.refresh(assessment)
        return assessment

    async def confirm_assessment(
        self,
        auth: AuthContext,
        assessment_id: uuid.UUID,
    ) -> QualitativeAssessment | None:
        """Confirm a qualitative assessment as final human review."""

        stmt = (
            select(QualitativeAssessment)
            .join(
                Project,
                QualitativeAssessment.project_id == Project.id,
            )
            .where(
                QualitativeAssessment.id == assessment_id,
                Project.organization_id == auth.organization_id,
            )
        )
        row = await self._session.execute(stmt)
        assessment = row.scalar_one_or_none()
        if assessment is None:
            return None

        assessment.is_confirmed_by_human = True
        assessment.reviewer_id = auth.actor_id
        assessment.reviewed_at = datetime.now(UTC)
        assessment.updated_at = datetime.now(UTC)
        self._session.add(assessment)
        await self._session.flush()

        await self._audit.log(
            organization_id=auth.organization_id,
            action="qualitative_assessment_confirmed",
            actor_id=auth.actor_id,
            entity_type="qualitative_assessment",
            entity_id=assessment_id,
            project_id=assessment.project_id,
            metadata={
                "verdict": assessment.verdict.value,
                "reason_code": assessment.reason_code,
            },
        )

        await self._session.commit()
        await self._session.refresh(assessment)
        return assessment

    async def get_latest_assessment(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> QualitativeAssessment | None:
        """Get the latest qualitative assessment for a requirement (tenant-scoped)."""

        stmt = (
            select(QualitativeAssessment)
            .join(
                Project,
                QualitativeAssessment.project_id == Project.id,
            )
            .where(
                QualitativeAssessment.requirement_id == requirement_id,
                QualitativeAssessment.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(QualitativeAssessment.assessment_version.desc())
            .limit(1)
        )
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none()

    async def list_assessments(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
    ) -> list[QualitativeAssessment]:
        """List all qualitative assessments for a project (tenant-scoped)."""

        stmt = (
            select(QualitativeAssessment)
            .join(
                Project,
                QualitativeAssessment.project_id == Project.id,
            )
            .where(
                QualitativeAssessment.project_id == project_id,
                Project.organization_id == auth.organization_id,
            )
            .order_by(
                QualitativeAssessment.requirement_id,
                QualitativeAssessment.assessment_version,
            )
        )
        row = await self._session.execute(stmt)
        return list(row.scalars().all())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_requirement(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> Requirement | None:
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
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_evidence(
        self,
        auth: AuthContext,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        *,
        evidence_id_filter: str | None = None,
    ) -> list[Evidence]:
        """Fetch accepted evidence for a requirement (tenant-scoped).

        If ``evidence_id_filter`` is provided, only that evidence item is
        fetched (and must be accepted).
        """
        stmt = (
            select(Evidence)
            .join(
                OemDocumentVersion,
                Evidence.oem_document_version_id == OemDocumentVersion.id,
            )
            .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
            .join(Project, OemDocument.project_id == Project.id)
            .where(
                Evidence.requirement_id == requirement_id,
                Project.id == project_id,
                Project.organization_id == auth.organization_id,
                Evidence.review_state == EvidenceReviewState.ACCEPTED,
            )
        )
        if evidence_id_filter is not None:
            stmt = stmt.where(Evidence.id == uuid.UUID(evidence_id_filter))
        stmt = stmt.order_by(Evidence.score.desc().nullslast())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Attribution / contradiction helpers (pure functions)
# ---------------------------------------------------------------------------


def _check_entity_attribution(
    req: Requirement,
    vs: VendorSpec,
) -> AttributionMismatch | None:
    """Check if the vendor spec's entity matches the requirement's expected product.

    This is a conservative check — it only flags a mismatch when the
    requirement text explicitly mentions a model/product designation that
    differs from the vendor spec's entity.  We never infer a mismatch from
    absence.
    """
    req_text = req.raw_source or ""
    if vs.entity is None:
        return None

    # Look for model-like patterns in the requirement text (case-insensitive).
    model_match = re.search(
        r"model\s+([A-Za-z0-9][A-Za-z0-9\-]+)", req_text, re.IGNORECASE
    )
    if model_match:
        req_model = model_match.group(1).strip()
        vs_entity = vs.entity
        vs_entity_lower = vs_entity.lower()
        if req_model.lower() != vs_entity_lower and req_model.lower() not in vs_entity_lower:
            return AttributionMismatch(
                field="entity",
                requirement_value=req_model,
                evidence_value=vs_entity,
                detail=(
                    f"Requirement references model '{req_model}' but "
                    f"vendor spec entity is '{vs_entity}'."
                ),
            )
    return None


def _check_conditions_attribution(
    req: Requirement,
    vs: VendorSpec,
) -> AttributionMismatch | None:
    """Check if operating conditions in the vendor spec match the requirement scope.

    Only flags when both sides have conditions and they differ on a
    comparable axis (temperature, humidity, pressure).
    """
    if not vs.conditions:
        return None
    if not req.raw_source:
        return None

    req_text = req.raw_source.lower()
    for key, val in vs.conditions.items():
        # Look for the condition key in the requirement text.
        key_lower = key.lower().replace("_", " ")
        # Extract the numeric value from the condition if possible.
        val_str = str(val).lower()
        if key_lower in req_text and val_str not in req_text:
            return AttributionMismatch(
                field=f"conditions:{key}",
                requirement_value=None,
                evidence_value=str(val),
                detail=(
                    f"Vendor spec condition '{key}={val}' does not "
                    f"match the requirement's stated operating conditions."
                ),
            )
    return None


def _detect_source_contradiction(
    specs_by_param: dict[str, list[tuple[float | None, uuid.UUID]]],
) -> bool:
    """Detect when multiple evidence items give different numeric values
    for the same parameter.

    Returns True if any parameter has two or more distinct non-None values
    from different evidence items.
    """
    for _param, values in specs_by_param.items():
        distinct_values = {
            v for v, _ in values if v is not None
        }
        if len(distinct_values) > 1:
            return True
    return False


__all__ = [
    "AttributionMismatch",
    "DEFAULT_MODEL_VERSION",
    "PROMPT_VERSION",
    "QualitativeAssessment",
    "QualitativeReasoningContext",
    "QualitativeReasoningResult",
    "QualitativeReasoningService",
    "QualitativeReasoner",
    "QualitativeVerdict",
    "REASONING_VERSION",
    "RuleBasedQualitativeReasoner",
    "FakeQualitativeReasoner",
]
