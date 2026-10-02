"""Deterministic keyword retrieval over OEM evidence (CP50).

The retrieval engine searches ``OemTextSegment`` rows for terms drawn from a
requirement and returns ranked evidence candidates.  Every candidate is
source-linked: the :class:`EvidenceLocation` records exact page/offset/bbox
so "every candidate opens its actual OEM source" (checkpoint guardrail).

Design principles (AGENTS.md Phase 2 guardrails):
* Never infer compliance — only propose *candidates*.
* Never fabricate a source citation or score; score comes from deterministic
  TF-IDF-style term-frequency weighting.
* Zero/weak retrieval is treated as **missing evidence**, not non-compliance.
* Retrieval config, version, and ranking signals are recorded in
  ``Evidence.retrieval_config`` for auditability.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from tender_compliance_api.audit.service import AuditService
from tender_compliance_api.auth.context import AuthContext
from tender_compliance_api.db.models import (
    DocumentProcessingStatus,
    DocumentVersion,
    Evidence,
    EvidenceLocation,
    EvidenceReviewState,
    OemDocument,
    OemDocumentVersion,
    OemTextSegment,
    Project,
    Requirement,
    TenderDocument,
)

#: Retrieval engine version — recorded on every Evidence row for audit.
RETRIEVAL_VERSION = "cp50-keyword-v1"

# Stop-words trimmed before indexing/search (keeps scoring deterministic).
_STOP_WORDS = frozenset(
    {
        "the", "a", "an", "of", "in", "on", "at", "to", "for", "and",
        "or", "but", "with", "by", "from", "is", "are", "be", "was",
        "were", "been", "has", "have", "had", "shall", "should", "will",
        "would", "can", "could", "may", "might", "must",
    }
)

# Tokens: letters, digits, and hyphens inside words (e.g. "6061-T6").
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")


@dataclass(frozen=True)
class RetrievalHit:
    """A single scored segment hit (internal use)."""

    segment: OemTextSegment
    score: float
    matched_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceCandidate:
    """A proposed evidence candidate returned to the caller.

    Each candidate bundles the best-matching segment with a deterministic
    score and the list of query terms that matched.
    """

    oem_document_version_id: str
    segment_id: str
    score: float
    matched_terms: list[str]
    source_text: str | None
    page_number: int
    char_start: int | None
    char_end: int | None
    ocr_confidence: float | None


def tokenize(text: str) -> list[str]:
    """Lowercase, extract word tokens, drop stop-words."""
    return [
        tok
        for tok in (m.group(0) for m in _TOKEN_RE.finditer(text.lower()))
        if tok not in _STOP_WORDS
    ]


class RetrievalService:
    """Deterministic keyword retrieval over OEM text segments (CP50).

    Construct with an :class:`AsyncSession`.  All methods are tenant-scoped:
    every query is joined through ``OemDocument → Project →
    organization_id`` to enforce org isolation at the database level.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    # ------------------------------------------------------------------
    # Term-frequency / document-frequency scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _tf(term: str, tokens: list[str]) -> float:
        """Raw term frequency (1 + log tf)."""
        count = tokens.count(term)
        if count == 0:
            return 0.0
        return 1.0 + math.log(count)

    @staticmethod
    def _idf(term: str, doc_freq: int, doc_count: int) -> float:
        """Smoothed inverse document frequency."""
        if doc_freq == 0:
            return 0.0
        return math.log((1 + doc_count) / (1 + doc_freq)) + 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def propose_evidence(
        self,
        auth: AuthContext,
        project_id: str,
        requirement_id: str,
        query_terms: list[str],
        *,
        k: int = 10,
    ) -> list[EvidenceCandidate]:
        """Search OEM text segments for *query_terms* and return ranked hits.

        Args:
            auth: Authenticated context (organization_id for tenant scope).
            project_id: UUID of the project that owns the requirement.
            requirement_id: UUID of the requirement being investigated.
            query_terms: Normalized terms to match against OEM text segments.
            k: Maximum number of candidates to return.

        Returns:
            A list of :class:`EvidenceCandidate` sorted by score descending.
            If no segments match, returns an empty list (zero retrieval =
            missing evidence, not a non-compliance verdict).
        """
        if not query_terms or k <= 0:
            return []

        # Normalize terms to tokens (lowercase, deduplication).
        terms = []
        seen: set[str] = set()
        for raw in query_terms:
            for tok in tokenize(raw):
                if tok not in seen:
                    seen.add(tok)
                    terms.append(tok)
        if not terms:
            return []

        # --- Tenant-scoped segment lookup ---
        # Join OemTextSegment -> OemDocumentVersion -> OemDocument -> Project
        # -> organization_id so cross-org segments never leak.
        stmt = (
            select(OemTextSegment)
            .join(
                OemDocumentVersion,
                OemTextSegment.oem_document_version_id
                == OemDocumentVersion.id,
            )
            .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
            .join(Project, OemDocument.project_id == Project.id)
            .where(
                and_(
                    OemDocument.project_id == uuid.UUID(project_id),
                    Project.organization_id == auth.organization_id,
                    OemDocumentVersion.processing_status
                    != DocumentProcessingStatus.FAILED,
                )
            )
        )
        result = await self._session.execute(stmt)
        segments = result.scalars().all()
        if not segments:
            return []

        # --- Compute TF-IDF-style scores ---
        doc_count = len(segments)
        # Document frequency per term.
        token_lists: list[list[str]] = []
        doc_freq: dict[str, int] = {}
        for seg in segments:
            tokens = tokenize(seg.text)
            token_lists.append(tokens)
            for t in set(tokens):
                doc_freq[t] = doc_freq.get(t, 0) + 1

        hits: list[RetrievalHit] = []
        for i, seg in enumerate(segments):
            tokens = token_lists[i]
            score = 0.0
            matched: list[str] = []
            for term in terms:
                tf = self._tf(term, tokens)
                if tf > 0:
                    matched.append(term)
                    idf = self._idf(term, doc_freq.get(term, 0), doc_count)
                    score += tf * idf
            if score > 0:
                hits.append(
                    RetrievalHit(
                        segment=seg,
                        score=score,
                        matched_terms=matched,
                    )
                )

        # Sort by score descending, take top-k.
        hits.sort(key=lambda h: h.score, reverse=True)
        top = hits[:k]

        candidates = [
            EvidenceCandidate(
                oem_document_version_id=str(h.segment.oem_document_version_id),
                segment_id=str(h.segment.id),
                score=h.score,
                matched_terms=h.matched_terms,
                source_text=h.segment.text,
                page_number=h.segment.page_number,
                char_start=h.segment.start_char,
                char_end=h.segment.end_char,
                ocr_confidence=h.segment.ocr_confidence,
            )
            for h in top
        ]

        # --- Audit the retrieval attempt ---
        await self._audit.log(
            organization_id=auth.organization_id,
            action="evidence.retrieval",
            actor_id=auth.actor_id,
            entity_type="requirement",
            entity_id=uuid.UUID(requirement_id),
            project_id=uuid.UUID(project_id),
            metadata={
                "retrieval_version": RETRIEVAL_VERSION,
                "query_terms": terms,
                "num_terms": len(terms),
                "num_segments_searched": doc_count,
                "num_candidates_returned": len(candidates),
                "top_score": candidates[0].score if candidates else None,
            },
        )

        return candidates

    async def persist_evidence(
        self,
        auth: AuthContext,
        project_id: str,
        requirement_id: str,
        candidates: list[EvidenceCandidate],
        *,
        retrieval_config: dict[str, Any] | None = None,
    ) -> list[Evidence]:
        """Persist proposed evidence candidates as Evidence + EvidenceLocation rows.

        Each candidate becomes one :class:`Evidence` row (PROPOSED state)
        with one :class:`EvidenceLocation` child.  Existing PROPOSED evidence
        for the same (requirement, oem_document_version) pair is not
        duplicated — the caller should check for existing candidates first.

        Args:
            auth: Authenticated context.
            project_id: UUID string of the project.
            requirement_id: UUID string of the requirement.
            candidates: List of candidates from :meth:`propose_evidence`.
            retrieval_config: Optional dict of query/config/version metadata.

        Returns:
            The created :class:`Evidence` rows (with their locations loaded).
        """
        req_id = uuid.UUID(requirement_id)
        proj_id = uuid.UUID(project_id)

        # --- Tenant-scoped requirement verification ---
        # Verify the requirement belongs to the authenticated org's project
        # before creating any Evidence rows.  This enforces isolation at the
        # service layer (AGENTS.md: "every data boundary"), not just the
        # route layer.
        req_check = (
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
                and_(
                    Requirement.id == req_id,
                    Project.id == proj_id,
                    Project.organization_id == auth.organization_id,
                )
            )
        )
        req_result = await self._session.execute(req_check)
        if req_result.scalar_one_or_none() is None:
            return []

        created: list[Evidence] = []
        for cand in candidates:
            evidence = Evidence(
                requirement_id=req_id,
                oem_document_version_id=uuid.UUID(
                    cand.oem_document_version_id
                ),
                score=cand.score,
                retrieval_method="keyword",
                retrieval_config={
                    "version": RETRIEVAL_VERSION,
                    "query_terms": cand.matched_terms,
                    **(retrieval_config or {}),
                },
                review_state=EvidenceReviewState.PROPOSED,
                actor_id=auth.actor_id,
            )
            self._session.add(evidence)
            await self._session.flush()

            location = EvidenceLocation(
                evidence_id=evidence.id,
                oem_text_segment_id=uuid.UUID(cand.segment_id),
                oem_document_version_id=uuid.UUID(
                    cand.oem_document_version_id
                ),
                page_number=cand.page_number,
                char_start=cand.char_start,
                char_end=cand.char_end,
                ocr_confidence=cand.ocr_confidence,
                location_type=(
                    "approximate" if cand.ocr_confidence is not None
                    else "exact"
                ),
                source_text=cand.source_text,
            )
            self._session.add(location)
            await self._session.flush()

            created.append(evidence)

        # Audit the persistence.
        await self._audit.log(
            organization_id=auth.organization_id,
            action="evidence.proposed",
            actor_id=auth.actor_id,
            entity_type="requirement",
            entity_id=req_id,
            project_id=proj_id,
            metadata={
                "retrieval_version": RETRIEVAL_VERSION,
                "num_candidates": len(candidates),
            },
        )

        await self._session.commit()
        return created

    async def list_evidence(
        self,
        auth: AuthContext,
        project_id: str,
        requirement_id: str,
        *,
        review_state: str | None = None,
    ) -> list[Evidence]:
        """List evidence candidates for a requirement (tenant-scoped).

        Optionally filter by review_state.  Results are ordered by score
        descending so the strongest candidates appear first.
        """
        req_id = uuid.UUID(requirement_id)
        proj_id = uuid.UUID(project_id)

        stmt = (
            select(Evidence)
            .join(
                OemDocumentVersion,
                Evidence.oem_document_version_id == OemDocumentVersion.id,
            )
            .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
            .join(Project, OemDocument.project_id == Project.id)
            .where(
                and_(
                    Evidence.requirement_id == req_id,
                    Project.organization_id == auth.organization_id,
                    Project.id == proj_id,
                )
            )
        )
        if review_state is not None:
            stmt = stmt.where(
                Evidence.review_state == review_state
            )
        stmt = stmt.order_by(Evidence.score.desc().nullslast())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def curate_evidence(
        self,
        auth: AuthContext,
        evidence_id: str,
        review_state: str,
    ) -> Evidence:
        """Set the review state of an evidence candidate (accept/reject).

        Tenant-scoped: can only update evidence belonging to the authenticated
        organization's project.
        """
        eid = uuid.UUID(evidence_id)

        # Look up with tenant scope — also fetch project_id for audit.
        stmt = (
            select(Evidence, OemDocument.project_id)
            .join(
                OemDocumentVersion,
                Evidence.oem_document_version_id == OemDocumentVersion.id,
            )
            .join(OemDocument, OemDocumentVersion.document_id == OemDocument.id)
            .join(Project, OemDocument.project_id == Project.id)
            .where(
                and_(
                    Evidence.id == eid,
                    Project.organization_id == auth.organization_id,
                )
            )
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None  # type: ignore[return-value]
        evidence = row[0]
        project_id_val = row[1]

        prev_state = evidence.review_state
        evidence.review_state = EvidenceReviewState(review_state)
        evidence.actor_id = auth.actor_id

        await self._audit.log(
            organization_id=auth.organization_id,
            action="evidence.curation",
            actor_id=auth.actor_id,
            entity_type="evidence",
            entity_id=eid,
            project_id=project_id_val,
            metadata={
                "from_state": prev_state.value,
                "to_state": review_state,
            },
        )

        await self._session.commit()
        await self._session.refresh(evidence)
        return evidence
