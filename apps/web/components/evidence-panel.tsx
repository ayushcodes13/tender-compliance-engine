"use client";

import { Check, Search, X, AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";

import {
  api,
  EvidenceCandidateResponse,
  EvidenceResponse,
  EvidenceReviewState,
} from "@/lib/api/client";

type EvidencePanelProps = {
  projectId: string;
  requirementId: string;
  /** Terms to search when proposing. Usually derived from the requirement text. */
  queryTerms: string[];
  /** Called when evidence is curated so the parent can refresh. */
  onEvidenceChanged?: () => void;
};

/**
 * Evidence review panel (CP51).

 * Shows:
 * 1. A "Propose Evidence" button that runs deterministic keyword retrieval.
 * 2. A list of persisted evidence candidates — **score is visually
 *    secondary**; the source text is the primary content (guardrail: high
 *    retrieval score must never be shown as compliant).
 * 3. Accept / Reject buttons for curating each candidate.
 * 4. Previously curated evidence (accepted/rejected), clearly labeled as
 *    human-curated.
 *
 * Every candidate shows its source linkage: OEM document name, version,
 * page number, and the verbatim source text snippet. OCR confidence is
 * surfaced when present.
 */
export function EvidencePanel(props: EvidencePanelProps) {
  const { projectId, requirementId, queryTerms, onEvidenceChanged } = props;

  const [proposals, setProposals] = useState<EvidenceCandidateResponse[]>([]);
  const [proposing, setProposing] = useState(false);
  const [proposeError, setProposeError] = useState<string | null>(null);

  const [persisted, setPersisted] = useState<EvidenceResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [curating, setCurating] = useState<string | null>(null);

  // Load persisted evidence on mount and after changes.
  const loadPersisted = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await api.fetchEvidence(projectId, requirementId);
      setPersisted(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evidence");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPersisted();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, requirementId]);

  const handlePropose = async (persist: boolean) => {
    if (!queryTerms.length) {
      setProposeError("No query terms available — cannot propose evidence");
      return;
    }
    setProposing(true);
    setProposeError(null);
    try {
      const candidates = await api.proposeEvidence(projectId, requirementId, {
        query_terms: queryTerms,
        k: 10,
        persist,
      });
      if (persist) {
        // Candidates were persisted as PROPOSED evidence — refresh the list.
        setProposals([]);
        await loadPersisted();
        onEvidenceChanged?.();
      } else {
        setProposals(candidates);
      }
    } catch (err) {
      setProposeError(
        err instanceof Error ? err.message : "Failed to propose evidence"
      );
    } finally {
      setProposing(false);
    }
  };

  const handleCurate = async (
    id: string,
    state: EvidenceReviewState
  ) => {
    setCurating(id);
    try {
      await api.curateEvidence(projectId, requirementId, id, state);
      await loadPersisted();
      onEvidenceChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to curate evidence");
    } finally {
      setCurating(null);
    }
  };

  const proposed = persisted.filter((e) => e.review_state === "proposed");
  const accepted = persisted.filter((e) => e.review_state === "accepted");
  const rejected = persisted.filter((e) => e.review_state === "rejected");

  return (
    <section className="evidence-section">
      <div className="evidence-section-heading">
        <span>
          <Search size={13} aria-hidden="true" />
          Evidence for this requirement
        </span>
      </div>

      {/* Query terms display + propose buttons */}
      <div style={{ marginBottom: "12px" }}>
        {queryTerms.length > 0 ? (
          <p className="field-help">
            Search terms: {queryTerms.join(", ")}
          </p>
        ) : (
          <p className="field-help" style={{ color: "var(--warning-text)" }}>
            No query terms available — cannot propose evidence automatically.
          </p>
        )}
        <div style={{ display: "flex", gap: "6px", marginTop: "6px" }}>
          <button
            type="button"
            className="button button-primary button-small"
            onClick={() => handlePropose(false)}
            disabled={proposing || queryTerms.length === 0}
          >
            {proposing ? "Searching…" : "Propose (preview)"}
          </button>
          <button
            type="button"
            className="button button-secondary button-small"
            onClick={() => handlePropose(true)}
            disabled={proposing || queryTerms.length === 0}
          >
            {proposing ? "Saving…" : "Propose & persist"}
          </button>
        </div>
      </div>

      {proposeError ? (
        <p className="save-error" role="alert">
          {proposeError}
        </p>
      ) : null}

      {/* Proposed candidates (from retrieval, not yet persisted) */}
      {proposals.length > 0 ? (
        <div style={{ marginBottom: "16px" }}>
          <div className="evidence-section-heading">
            <span>Retrieval candidates ({proposals.length})</span>
          </div>
          <p className="field-help">
            System-proposed candidates (not yet persisted). Scores are for
            ranking only — do not interpret as compliance evidence.
          </p>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {proposals.map((cand) => (
              <li
                key={cand.oem_document_version_id}
                style={{
                  padding: "8px 0",
                  borderBottom: "1px solid var(--border-light)",
                  fontSize: "9.5px",
                }}
              >
                <CandidateCard candidate={cand} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Persisted evidence */}
      {loading ? (
        <p style={{ color: "var(--text-tertiary)" }}>Loading evidence…</p>
      ) : error ? (
        <p className="save-error" role="alert">
          {error}
        </p>
      ) : persisted.length === 0 ? (
        <p className="field-help">
          No evidence has been proposed yet. Click "Propose &amp; persist"
          to run a deterministic keyword search and create evidence candidates.
        </p>
      ) : (
        <div>
          {/* Proposed (persisted but not yet curated) */}
          {proposed.length > 0 ? (
            <>
              <div className="evidence-section-heading">
                <span>
                  <AlertCircle size={12} aria-hidden="true" />
                  Awaiting curation ({proposed.length})
                </span>
              </div>
              {proposed.map((ev) => (
                <EvidenceItemRow
                  key={ev.id}
                  evidence={ev}
                  curating={curating === ev.id}
                  onCurate={handleCurate}
                  showCurateButtons={true}
                />
              ))}
            </>
          ) : null}

          {/* Accepted */}
          {accepted.length > 0 ? (
            <>
              <div className="evidence-section-heading">
                <span>
                  <Check size={12} aria-hidden="true" />
                  Accepted ({accepted.length})
                </span>
              </div>
              {accepted.map((ev) => (
                <EvidenceItemRow
                  key={ev.id}
                  evidence={ev}
                  curating={curating === ev.id}
                  onCurate={handleCurate}
                  showCurateButtons={false}
                />
              ))}
            </>
          ) : null}

          {/* Rejected */}
          {rejected.length > 0 ? (
            <>
              <div className="evidence-section-heading">
                <span>
                  <X size={12} aria-hidden="true" />
                  Rejected ({rejected.length})
                </span>
              </div>
              {rejected.map((ev) => (
                <EvidenceItemRow
                  key={ev.id}
                  evidence={ev}
                  curating={curating === ev.id}
                  onCurate={handleCurate}
                  showCurateButtons={false}
                />
              ))}
            </>
          ) : null}
        </div>
      )}
    </section>
  );
}

/** Renders a single retrieval candidate (not yet persisted). */
function CandidateCard({
  candidate,
}: {
  candidate: EvidenceCandidateResponse;
}) {
  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "8px",
          marginBottom: "4px",
        }}
      >
        <div>
          <strong>{candidate.oem_document_display_name || "—"}</strong>
          <span style={{ color: "var(--text-tertiary)" }}>
            {" "}
            v{candidate.version_number} · Page {candidate.page_number}
          </span>
        </div>
        {/* Score is visually secondary (small, muted) */}
        <span style={{ color: "var(--text-tertiary)", fontSize: "8px" }}>
          relevance: {candidate.score.toFixed(2)}
        </span>
      </div>
      {candidate.source_text ? (
        <blockquote style={{ fontSize: "10.5px" }}>
          {candidate.source_text}
        </blockquote>
      ) : null}
      {candidate.matched_terms.length > 0 ? (
        <div style={{ marginTop: "4px" }}>
          {candidate.matched_terms.map((term) => (
            <span
              key={term}
              className="precision-pill"
              style={{ marginRight: "4px" }}
            >
              {term}
            </span>
          ))}
        </div>
      ) : null}
      <p className="field-help" style={{ marginTop: "4px" }}>
        System-proposed — not approved evidence. Persist and accept to
        register as reviewed proof.
      </p>
    </div>
  );
}

/** Renders a single persisted evidence item with accept/reject controls. */
function EvidenceItemRow({
  evidence,
  curating,
  onCurate,
  showCurateButtons,
}: {
  evidence: EvidenceResponse;
  curating: boolean;
  onCurate: (id: string, state: EvidenceReviewState) => void;
  showCurateButtons: boolean;
}) {
  const state = evidence.review_state;

  return (
    <div
      style={{
        padding: "8px 0",
        borderBottom: "1px solid var(--border-light)",
        fontSize: "9.5px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "8px",
          marginBottom: "4px",
        }}
      >
        <div>
          <span
            style={{
              color:
                state === "accepted"
                  ? "var(--text-primary)"
                  : state === "rejected"
                    ? "var(--text-tertiary)"
                    : "var(--text-secondary)",
              fontWeight: state === "accepted" ? 600 : 400,
              textDecoration:
                state === "rejected" ? "line-through" : "none",
            }}
          >
            {state === "proposed"
              ? "Awaiting review"
              : state === "accepted"
                ? "Accepted"
                : "Rejected"}
          </span>
        </div>
        {/* Score is always visually secondary */}
        <span style={{ color: "var(--text-tertiary)", fontSize: "8px" }}>
          score: {evidence.score !== null ? evidence.score.toFixed(2) : "—"}
        </span>
      </div>

      {evidence.locations.map((loc, idx) => (
        <div
          key={idx}
          style={{
            padding: "6px 0",
            fontSize: "10.5px",
          }}
        >
          <div
            style={{
              display: "flex",
              gap: "6px",
              alignItems: "baseline",
            }}
          >
            <span style={{ color: "var(--text-tertiary)" }}>
              p.{loc.page_number}
            </span>
            <span
              style={{
                color: "var(--text-tertiary)",
                fontSize: "8.5px",
              }}
            >
              {loc.location_type === "exact" ? "Exact" : "Approximate"}
            </span>
            {loc.ocr_confidence !== null &&
            loc.ocr_confidence !== undefined ? (
              <span style={{ color: "var(--text-tertiary)", fontSize: "8.5px" }}>
                OCR: {Math.round(loc.ocr_confidence * 100)}%
              </span>
            ) : null}
          </div>
          <div
            style={{
              marginTop: "3px",
              color:
                state === "rejected"
                  ? "var(--text-tertiary)"
                  : "var(--text-secondary)",
            }}
          >
            {loc.source_text || "—"}
          </div>
        </div>
      ))}

      {showCurateButtons && state === "proposed" ? (
        <div style={{ display: "flex", gap: "4px", marginTop: "6px" }}>
          <button
            type="button"
            className="button button-primary button-small"
            onClick={() => onCurate(evidence.id, "accepted")}
            disabled={curating}
          >
            <Check size={11} aria-hidden="true" />
            Accept
          </button>
          <button
            type="button"
            className="button button-secondary button-small"
            onClick={() => onCurate(evidence.id, "rejected")}
            disabled={curating}
          >
            <X size={11} aria-hidden="true" />
            Reject
          </button>
        </div>
      ) : null}
    </div>
  );
}
