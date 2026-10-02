"use client";

import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  FileText,
  Highlighter,
  Minus,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { SourceViewer } from "@/components/source-viewer";
import { EvidencePanel } from "@/components/evidence-panel";

import {
  api,
  DocumentItem,
  NoteSummary,
  RequirementDetail,
  RequirementListResponse,
  SourceAnchor,
} from "@/lib/api/client";

/** Status for the local UI state (mirrors backend RequirementReviewState). */
type RequirementStatus = "unreviewed" | "reviewed" | "needs_clarification" | "ocr_warning";

const statusLabel = (status: RequirementStatus): string => {
  if (status === "reviewed") return "Reviewed";
  if (status === "needs_clarification") return "Needs clarification";
  if (status === "ocr_warning") return "OCR warning";
  return "Unreviewed";
};

const statusClass = (status: RequirementStatus): string => {
  if (status === "reviewed") return "review-status review-status-reviewed";
  if (status === "ocr_warning") return "review-status review-status-ocr";
  if (status === "needs_clarification") return "review-status review-status-warning";
  return "review-status review-status-neutral";
};

const filterTabs: { key: string; label: string }[] = [
  { key: "all", label: "All" },
  { key: "review", label: "Needs review" },
  { key: "reviewed", label: "Reviewed" },
];

function useRequirements(
  projectId: string,
  documentId: string,
  version: number,
  search: string,
  filter: string,
) {
  const [data, setData] = useState<RequirementListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        // Map UI filter to backend review_state.
        let review_state: string | undefined;
        if (filter === "review") {
          review_state = undefined; // includes UNREVIEWED, NEEDS_CLARIFICATION, OCR_WARNING
        } else if (filter === "reviewed") {
          review_state = "reviewed";
        }

        const resp = await api.fetchRequirements(
          projectId,
          documentId,
          version,
          {
            search: search || undefined,
            review_state,
            limit: 200,
          }
        );
        setData(resp);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load requirements");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, documentId, version, search, filter]);

  return { data, loading, error };
}

/**
 * Real API-backed review workspace (CP37).
 *
 * Props come from the real project route — no seed data. All requirements,
 * counts, source metadata, and document labels are fetched from the backend.
 */
export function TenderReviewWorkspace(props: {
  projectId: string;
  documentId: string;
  version: number;
  document?: DocumentItem | null;
}) {
  const { projectId, documentId, version, document } = props;
  const [selectedId, setSelectedId] = useState<string>("");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [notesLoading, setNotesLoading] = useState(false);
  const [notesError, setNotesError] = useState<string | null>(null);
  const sourceRef = useRef<HTMLElement | null>(null);

  // Fetch requirements list from the real API.
  const { data: reqList, loading, error } = useRequirements(
    projectId,
    documentId,
    version,
    query,
    filter,
  );

  // Fetch selected requirement detail (with constraints and sources).
  const [selectedDetail, setSelectedDetail] = useState<RequirementDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedId) return;
    void (async () => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const detail = await api.fetchRequirement(projectId, documentId, version, selectedId);
        setSelectedDetail(detail);
      } catch (err) {
        setDetailError(err instanceof Error ? err.message : "Failed to load requirement");
      } finally {
        setDetailLoading(false);
      }
    })();
  }, [selectedId, projectId, documentId, version]);

  // Auto-select the first requirement when the list loads.
  useEffect(() => {
    if (reqList?.items && reqList.items.length > 0 && !selectedId) {
      setSelectedId(reqList.items[0].id);
    }
  }, [reqList, selectedId]);

  // Reset draft text and notes when selection changes.
  useEffect(() => {
    if (!selectedDetail) return;
    setDraftText(selectedDetail.normalized_text);
    setEditing(false);
    setNotes(selectedDetail.notes ?? []);
    const frame = window.requestAnimationFrame(() => {
      sourceRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [selectedDetail]);

  const selected = reqList?.items.find(
    (item) => item.id === selectedId
  );

  const reviewQueue = useMemo(() => {
    if (!reqList?.items) return [];
    return reqList.items.filter((item) => item.review_state !== "reviewed");
  }, [reqList]);

  const reviewIndex = reviewQueue.findIndex((item) => item.id === selected?.id);

  const goReview = (direction: number) => {
    if (reviewQueue.length === 0) return;
    const base = Math.max(reviewIndex, 0);
    const next = (base + direction + reviewQueue.length) % reviewQueue.length;
    setSelectedId(reviewQueue[next].id);
  };

  const saveNormalizedText = async () => {
    const nextText = draftText.trim();
    if (!nextText) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.editRequirementOrError(
        projectId,
        documentId,
        version,
        selectedId,
        {
          normalized_text: nextText,
          expected_updated_at: selectedDetail?.updated_at ?? undefined,
          note: null,
        }
      ).then((result) => {
        if (result.error) {
          throw new Error(
            result.error.message + " (conflicting edit detected)"
          );
        }
        if (result.data) {
          setSelectedDetail(result.data);
        }
      });
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
      setEditing(false);
    }
  };

  const markReviewed = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await api.markReviewed(projectId, documentId, version, selectedId);
      await api.fetchRequirement(projectId, documentId, version, selectedId)
        .then(setSelectedDetail)
        .catch(() => {});
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const reopenReview = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await api.reopenRequirement(projectId, documentId, version, selectedId);
      await api.fetchRequirement(projectId, documentId, version, selectedId)
        .then(setSelectedDetail)
        .catch(() => {});
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to update");
    } finally {
      setSaving(false);
    }
  };

  if (loading && !reqList) {
    return (
      <div className="project-workspace">
        <div className="source-stage">
          <div className="loading-shimmer" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="project-workspace">
        <div className="source-stage">
          <div className="empty-list">
            <CircleAlert size={18} aria-hidden="true" />
            <strong>Failed to load requirements</strong>
            <span>{error}</span>
          </div>
        </div>
      </div>
    );
  }

  if (!reqList || reqList.items.length === 0) {
    return (
      <div className="project-workspace">
        <header className="project-topbar">
          <div className="project-breadcrumbs">
            <Link href="/" className="breadcrumb-back" aria-label="Back to projects">
              <ArrowLeft size={15} aria-hidden="true" />
            </Link>
            <span className="breadcrumb-muted">Projects</span>
          </div>
        </header>
        <div className="source-stage">
          <div className="empty-list">
            <FileText size={18} aria-hidden="true" />
            <strong>No requirements yet</strong>
            <span>Requirements will appear here after extraction completes.</span>
          </div>
        </div>
      </div>
    );
  }

  // The selected requirement from the list.
  const selectedSummary = selected ?? reqList.items[0];
  // The detailed view (with constraints and sources) for the selected requirement.
  const detail = selectedDetail ?? null;
  const selectedStatus: RequirementStatus = (selectedSummary?.review_state ??
    "unreviewed") as RequirementStatus;
  // Use the first source anchor's page for source viewer navigation, if available.
  const selectedSources = detail?.sources ?? [];
  const sourcePage = selectedSources[0]?.page_number ?? 1;

  // Derive query terms from the requirement's normalized text for evidence
  // retrieval. This is a simple term extraction: lowercase, strip punctuation,
  // remove common English stop words. The retrieval engine on the backend
  // uses the same stop-word logic, so these terms feed directly into
  // deterministic TF-IDF search over OEM documents.
  const STOP_WORDS = new Set([
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "must", "shall", "should", "will", "may", "can",
  ]);
  const queryTerms = useMemo(() => {
    const rawText =
      detail?.normalized_text ?? selectedSummary?.normalized_text ?? "";
    if (!rawText) return [];
    const tokens = rawText
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((t) => t.length > 2 && !STOP_WORDS.has(t));
    // Deduplicate while preserving order, cap at 20 terms.
    const unique: string[] = [];
    const seen = new Set<string>();
    for (const t of tokens) {
      if (!seen.has(t)) {
        seen.add(t);
        unique.push(t);
      }
    }
    return unique.slice(0, 20);
  }, [detail?.normalized_text, selectedSummary?.normalized_text]);

  // Trigger evidence refresh from parent (e.g. after requirement review update).
  const [evidenceRevision, setEvidenceRevision] = useState(0);
  const refreshEvidence = () => setEvidenceRevision((n) => n + 1);

  return (
    <div className="project-workspace">
      <header className="project-topbar">
        <div className="project-breadcrumbs">
          <Link href="/" className="breadcrumb-back" aria-label="Back to projects">
            <ArrowLeft size={15} aria-hidden="true" />
          </Link>
          <span className="breadcrumb-muted">Projects</span>
          <span className="breadcrumb-separator">/</span>
          <strong>{document?.display_name ?? "Tender document"}</strong>
          <span className="project-id">
            v{version} · {reqList.total} requirements
          </span>
        </div>

        <div className="project-topbar-actions">
          <span className="saved-state">
            <Check size={13} aria-hidden="true" />
            Live data
          </span>
          <button className="icon-button" type="button" aria-label="Project options">
            <MoreHorizontal size={17} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="project-tabs" role="tablist" aria-label="Project sections">
        <button className="project-tab project-tab-active" role="tab" aria-selected="true" type="button">
          Requirements
          <span>{reqList.total}</span>
        </button>
        <button className="project-tab" role="tab" aria-selected="false" type="button" disabled>
          Documents
          <span>1</span>
        </button>
        <button className="project-tab" role="tab" aria-selected="false" type="button" disabled>
          Matrix
        </button>

        <div className="review-navigator" aria-label="Review queue navigation">
          <span className="review-navigator-label">
            <Highlighter size={13} aria-hidden="true" />
            Needs review
          </span>
          <strong>
            {reviewQueue.length === 0
              ? "0 of 0"
              : reviewIndex >= 0
                ? `${reviewIndex + 1} of ${reviewQueue.length}`
                : `— of ${reviewQueue.length}`}
          </strong>
          <button
            type="button"
            onClick={() => goReview(-1)}
            disabled={reviewQueue.length === 0}
            aria-label="Previous requirement needing review"
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => goReview(1)}
            disabled={reviewQueue.length === 0}
            aria-label="Next requirement needing review"
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="review-layout">
        {/* Left pane: requirements list */}
        <section className="requirements-pane" aria-label="Requirements">
          <div className="pane-heading">
            <div>
              <h1>Requirements</h1>
              <p>{reqList.total} extracted · source linked</p>
            </div>
            <button className="icon-button" type="button" aria-label="Requirement filters">
              <SlidersHorizontal size={16} aria-hidden="true" />
            </button>
          </div>

          <div className="requirement-search">
            <Search size={14} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search requirements"
              aria-label="Search requirements"
            />
          </div>

          <div className="filter-tabs" role="tablist" aria-label="Requirement filters">
            {filterTabs.map((tab) => (
              <button
                key={tab.key}
                className={filter === tab.key ? "filter-tab filter-tab-active" : "filter-tab"}
                type="button"
                onClick={() => setFilter(tab.key)}
              >
                {tab.label}
                {tab.key === "review" && reviewQueue.length > 0 && (
                  <span>{reviewQueue.length}</span>
                )}
              </button>
            ))}
          </div>

          <div className="requirement-list">
            {reqList.items.map((item) => {
              const active = item.id === selectedId;
              const itemStatus = item.review_state as RequirementStatus;
              const clause = item.clause_number ?? "—";
              return (
                <article
                  key={item.id}
                  className={
                    active ? "requirement-card requirement-card-active" : "requirement-card"
                  }
                >
                  <button
                    type="button"
                    className="requirement-card-main"
                    onClick={() => setSelectedId(item.id)}
                    aria-pressed={active}
                  >
                    <div className="requirement-meta-line">
                      <span>{item.id}</span>
                      <span>Clause {clause}</span>
                    </div>
                    <p>{item.normalized_text}</p>
                    <div className="requirement-card-bottom">
                      <span className={statusClass(itemStatus)}>
                        {itemStatus === "reviewed" ? (
                          <Check size={11} aria-hidden="true" />
                        ) : null}
                        {itemStatus === "ocr_warning" ? (
                          <CircleAlert size={11} aria-hidden="true" />
                        ) : null}
                        {itemStatus === "needs_clarification" ? (
                          <TriangleAlert size={11} aria-hidden="true" />
                        ) : null}
                        {statusLabel(itemStatus)}
                      </span>
                    </div>
                  </button>

                  {/* Source citation chip — uses real source data */}
                  {selectedSources
                    .filter((src) => src.requirement_id === item.id)
                    .map((src) => (
                      <span key={src.requirement_id} className="citation-wrap">
                        <button
                          type="button"
                          className="citation-chip"
                          onClick={() => setSelectedId(item.id)}
                          aria-label={`Open source on page ${src.page_number}`}
                        >
                          <FileText size={12} aria-hidden="true" />
                          {document?.display_name ?? "tender.pdf"} · p.{src.page_number}
                        </button>
                        <span className="citation-glance" role="tooltip">
                          <span className="citation-glance-label">Source evidence</span>
                          <strong>{document?.display_name ?? "Technical Tender"}</strong>
                          <p>{src.source_text ?? "(no source text)"}</p>
                          <small>
                            Page {src.page_number} · Clause {src.clause_number ?? "—"} ·{" "}
                            {src.location_type === "exact" ? "Exact" : "Approximate"}{" "}
                            anchor
                          </small>
                        </span>
                      </span>
                    ))}
                </article>
              );
            })}

            {reqList.items.length === 0 ? (
              <div className="empty-list">
                <Search size={18} aria-hidden="true" />
                <strong>No matching requirements</strong>
                <span>Try another search or filter.</span>
              </div>
            ) : null}
          </div>
        </section>

        {/* Middle pane: source viewer (real PNG + bbox overlay) */}
        <section className="source-pane" aria-label="Tender source document">
          {detailLoading ? (
            <div className="source-stage">
              <div className="loading-shimmer" />
            </div>
          ) : detailError ? (
            <div className="source-stage">
              <div className="empty-list">
                <CircleAlert size={18} aria-hidden="true" />
                <strong>Failed to load requirement</strong>
                <span>{detailError}</span>
              </div>
            </div>
          ) : (
            <SourceViewer
              projectId={projectId}
              documentId={documentId}
              version={version}
              pageNumber={sourcePage}
              totalPages={undefined}
              onPageChange={(page) => {
                /* Page navigation handled within SourceViewer */
              }}
            />
          )}
        </section>

        {/* Right pane: evidence and review */}
        <aside className="evidence-pane" aria-label="Requirement evidence and review">
          <div className="evidence-header">
            <div>
              <p className="eyebrow">Review</p>
              <h2>Requirement evidence</h2>
            </div>
            <span className={statusClass(selectedStatus)}>
              {statusLabel(selectedStatus)}
            </span>
          </div>

          <div className="evidence-scroll">
            {selectedSummary?.ocr_warning ? (
              <div className="review-alert">
                <CircleAlert size={16} aria-hidden="true" />
                <div>
                  <strong>OCR requires review</strong>
                  <p>
                    The source may contain OCR artifacts. Confirm the symbol and
                    unit against the rendered page before approving.
                  </p>
                </div>
              </div>
            ) : null}

            <section className="evidence-section">
              <div className="evidence-section-heading">
                <span>Source anchor</span>
                {selectedSources.length > 0 ? (
                  <span className="precision-pill">
                    {selectedSources[0].location_type === "exact"
                      ? "Exact"
                      : "Approximate"}
                  </span>
                ) : null}
              </div>

              <div className="source-reference">
                <span className="pdf-glyph">PDF</span>
                <div>
                  <strong>{document?.display_name ?? "Technical Tender"}</strong>
                  <p>
                    Page {sourcePage} · Clause{" "}
                    {selectedSources[0]?.clause_number ?? "—"}
                  </p>
                </div>
              </div>

              {selectedSources.length > 0 && selectedSources[0].source_text ? (
                <blockquote>{selectedSources[0].source_text}</blockquote>
              ) : (
                <p style={{ color: "var(--text-tertiary)" }}>
                  No source text available.
                </p>
              )}

              {detail?.constraints && detail.constraints.length > 0 ? (
                <div style={{ marginTop: "12px" }}>
                  <div
                    className="evidence-section-heading"
                    style={{ marginBottom: "8px" }}
                  >
                    <span>Extracted constraints</span>
                  </div>
                  <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {detail.constraints.map((c) => (
                      <li
                        key={c.id}
                        style={{
                          padding: "4px 0",
                          borderBottom: "1px solid var(--border-light)",
                          fontSize: "12px",
                        }}
                      >
                        <strong>{c.parameter}</strong>
                        {c.operator
                          ? `: ${c.operator} ${c.numeric_value ?? ""}`
                          : ""}
                        {c.unit ? ` ${c.unit}` : ""}
                        {c.tolerance ? ` (±${c.tolerance})` : ""}
                        {c.qualitative_condition
                          ? `: ${c.qualitative_condition}`
                          : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <button
                type="button"
                className="text-action"
                onClick={() => {
                  sourceRef.current?.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  });
                }}
              >
                <Highlighter size={13} aria-hidden="true" />
                Locate in source
              </button>
            </section>

            {/* Evidence review panel (CP51) */}
            {selectedId ? (
              <EvidencePanel
                projectId={projectId}
                requirementId={selectedId}
                queryTerms={queryTerms}
                onEvidenceChanged={refreshEvidence}
              />
            ) : null}

            <section className="evidence-section">
              <div className="evidence-section-heading">
                <span>Normalized requirement</span>
                {!editing ? (
                  <button
                    type="button"
                    className="tiny-action"
                    onClick={() => setEditing(true)}
                  >
                    <Pencil size={12} aria-hidden="true" />
                    Edit
                  </button>
                ) : null}
              </div>

              {editing ? (
                <>
                  <textarea
                    className="review-textarea"
                    value={draftText}
                    onChange={(event) => setDraftText(event.target.value)}
                    rows={5}
                    aria-label="Normalized requirement"
                  />
                  <div className="inline-actions">
                    <button
                      type="button"
                      className="button button-secondary button-small"
                      onClick={() => {
                        setDraftText(selectedSummary?.normalized_text ?? "");
                        setEditing(false);
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="button button-primary button-small"
                      onClick={saveNormalizedText}
                      disabled={!draftText.trim() || saving}
                    >
                      {saving ? "Saving…" : "Save change"}
                    </button>
                  </div>
                  {saveError ? (
                    <p className="save-error" role="alert">
                      {saveError}
                    </p>
                  ) : null}
                </>
              ) : (
                <div className="normalized-card">
                  <span className="normalized-id">{selectedSummary?.id}</span>
                  <p>{selectedSummary?.normalized_text}</p>
                </div>
              )}

              <dl className="requirement-facts">
                <div>
                  <dt>Status</dt>
                  <dd>{statusLabel(selectedStatus)}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>
                    Page {sourcePage} ·{" "}
                    {selectedSources[0]?.clause_number ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt>Constraints</dt>
                  <dd>{detail?.constraints?.length ?? 0} extracted</dd>
                </div>
              </dl>
            </section>

            {selectedDetail?.revisions && selectedDetail.revisions.length > 0 ? (
              <section className="evidence-section">
                <div className="evidence-section-heading">
                  <span>Revision history ({selectedDetail.revisions.length})</span>
                </div>
                <ul className="revision-list">
                  {selectedDetail.revisions.map((rev) => (
                    <li key={rev.id} className="revision-item">
                      <span className="revision-prev-text">{rev.previous_normalized_text}</span>
                      <span className="revision-meta">
                        {new Date(rev.created_at).toLocaleString()}
                        {rev.note ? ` — ${rev.note}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="field-help">
                  Immutable log of every material edit. raw_source is never
                  modified.
                </p>
              </section>
            ) : null}

            <section className="evidence-section">
              <div className="evidence-section-heading">
                <span>Reviewer notes ({notes.length})</span>
              </div>

              {notes.length > 0 ? (
                <ul className="note-list">
                  {notes.map((note) => (
                    <li key={note.id} className="note-item">
                      <p className="note-text">{note.text}</p>
                      <span className="note-meta">
                        {new Date(note.created_at).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}

              <textarea
                className="review-textarea note-textarea"
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                rows={4}
                placeholder="Add a note about wording, OCR, or source interpretation…"
                aria-label="Reviewer note"
                disabled={notesLoading}
              />
              {notesError ? (
                <p className="save-error" role="alert">{notesError}</p>
              ) : null}
              <button
                type="button"
                className="button button-secondary button-small"
                onClick={async () => {
                  if (!noteText.trim() || !selectedId) return;
                  setNotesLoading(true);
                  setNotesError(null);
                  try {
                    await api.addNote(
                      projectId,
                      documentId,
                      version,
                      selectedId,
                      { text: noteText.trim() }
                    );
                    setNoteText("");
                    // Reload detail to refresh notes list.
                    const detail = await api.fetchRequirement(
                      projectId,
                      documentId,
                      version,
                      selectedId
                    );
                    setNotes(detail.notes ?? []);
                  } catch (err) {
                    setNotesError(
                      err instanceof Error ? err.message : "Failed to add note"
                    );
                  } finally {
                    setNotesLoading(false);
                  }
                }}
                disabled={!noteText.trim() || notesLoading}
              >
                {notesLoading ? "Saving…" : "Add note"}
              </button>
            </section>
          </div>

          <div className="evidence-footer">
            {selectedStatus === "reviewed" ? (
              <>
                <span className="reviewed-message">
                  <Check size={14} aria-hidden="true" /> Reviewed
                </span>
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={reopenReview}
                >
                  Reopen
                </button>
              </>
            ) : (
              <>
                <span className="footer-hint">
                  Confirm wording against the highlighted source.
                </span>
                <button
                  type="button"
                  className="button button-primary"
                  onClick={markReviewed}
                >
                  <Check size={14} aria-hidden="true" />
                  Mark reviewed
                </button>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

/**
 * Isolated demo workspace — uses seed data for UI development without
 * a running backend. This is NOT used by real project routes.
 */
export function DemoTenderReviewWorkspace() {
  return (
    <div className="project-workspace">
      <div className="source-stage">
        <div className="empty-list">
          <FileText size={18} aria-hidden="true" />
          <strong>Demo mode</strong>
          <span>
            The demo workspace has been removed. Use a real project route
            (e.g. /projects/{"{id}"}/review) to see live data.
          </span>
        </div>
      </div>
    </div>
  );
}
