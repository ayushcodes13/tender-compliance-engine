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

type RequirementStatus = "UNREVIEWED" | "REVIEWED" | "NEEDS_CLARIFICATION" | "OCR_WARNING";
type Filter = "all" | "review" | "reviewed";

type Requirement = {
  id: string;
  clause: string;
  category: string;
  mandatory: boolean;
  page: number;
  status: RequirementStatus;
  rawText: string;
  normalizedText: string;
  sourceText: string;
  contextBefore: string;
  contextAfter: string;
  note: string;
  locationPrecision: "Exact" | "Approximate";
};

const seedRequirements: Requirement[] = [
  {
    id: "REQ-001",
    clause: "4.2.1",
    category: "Performance",
    mandatory: true,
    page: 12,
    status: "NEEDS_CLARIFICATION",
    rawText: "Dynamic range: minimum 150 dB over the specified operating bandwidth.",
    normalizedText: "Dynamic range shall be ≥ 150 dB over the specified operating bandwidth.",
    sourceText: "Dynamic range: minimum 150 dB over the specified operating bandwidth.",
    contextBefore:
      "The proposed acquisition unit shall meet the following performance specifications under normal operating conditions.",
    contextAfter:
      "The bidder shall submit the manufacturer datasheet identifying the stated performance parameter.",
    note: "",
    locationPrecision: "Exact",
  },
  {
    id: "REQ-002",
    clause: "4.2.2",
    category: "Environmental",
    mandatory: true,
    page: 12,
    status: "UNREVIEWED",
    rawText: "Operating temperature shall be -20°C to +60°C.",
    normalizedText: "Operating temperature range shall cover -20°C to +60°C.",
    sourceText: "Operating temperature shall be -20°C to +60°C.",
    contextBefore: "Environmental ratings shall apply to the complete offered configuration.",
    contextAfter: "Storage conditions and transport limits shall be stated separately by the bidder.",
    note: "",
    locationPrecision: "Exact",
  },
  {
    id: "REQ-003",
    clause: "4.3.1",
    category: "Interface",
    mandatory: true,
    page: 13,
    status: "REVIEWED",
    rawText: "The system shall provide not less than four isolated analogue input channels.",
    normalizedText: "System shall provide at least 4 isolated analogue input channels.",
    sourceText: "The system shall provide not less than four isolated analogue input channels.",
    contextBefore: "Input and output interfaces shall be accessible without disassembling the enclosure.",
    contextAfter: "All channel connectors shall be identified permanently on the front or rear panel.",
    note: "Wording normalized; quantity and isolation requirement preserved.",
    locationPrecision: "Exact",
  },
  {
    id: "REQ-004",
    clause: "4.3.4",
    category: "Resolution",
    mandatory: true,
    page: 14,
    status: "OCR_WARNING",
    rawText: "Display/readout resolution: 1 μm or better.",
    normalizedText: "Display/readout resolution shall be ≤ 1 μm.",
    sourceText: "Display/readout resolution: 1 μm or better.",
    contextBefore: "The digital position indication shall remain visible during manual and automated movement.",
    contextAfter: "The accuracy specification shall be declared independently of the display resolution.",
    note: "",
    locationPrecision: "Approximate",
  },
  {
    id: "REQ-005",
    clause: "5.1.2",
    category: "Documentation",
    mandatory: false,
    page: 18,
    status: "UNREVIEWED",
    rawText: "Calibration certificate traceable to a national or international standard shall be supplied.",
    normalizedText: "Supply a calibration certificate traceable to a national or international standard.",
    sourceText: "Calibration certificate traceable to a national or international standard shall be supplied.",
    contextBefore: "Documentation supplied with the equipment shall be in English and specific to the offered model.",
    contextAfter: "Certificates shall identify the equipment serial number wherever applicable.",
    note: "",
    locationPrecision: "Exact",
  },
  {
    id: "REQ-006",
    clause: "6.2",
    category: "Warranty",
    mandatory: true,
    page: 21,
    status: "REVIEWED",
    rawText: "Comprehensive warranty for a minimum period of 24 months from acceptance.",
    normalizedText: "Comprehensive warranty shall be at least 24 months from acceptance.",
    sourceText: "Comprehensive warranty for a minimum period of 24 months from acceptance.",
    contextBefore: "Warranty obligations apply to the full supplied system including accessories and software.",
    contextAfter: "Response time and escalation contacts shall be provided before final acceptance.",
    note: "",
    locationPrecision: "Exact",
  },
];

function statusLabel(status: RequirementStatus) {
  if (status === "REVIEWED") return "Reviewed";
  if (status === "NEEDS_CLARIFICATION") return "Needs clarification";
  if (status === "OCR_WARNING") return "OCR warning";
  return "Unreviewed";
}

function statusClass(status: RequirementStatus) {
  if (status === "REVIEWED") return "review-status review-status-reviewed";
  if (status === "OCR_WARNING") return "review-status review-status-ocr";
  if (status === "NEEDS_CLARIFICATION") return "review-status review-status-warning";
  return "review-status review-status-neutral";
}

export function TenderReviewWorkspace() {
  const [requirements, setRequirements] = useState(seedRequirements);
  const [selectedId, setSelectedId] = useState(seedRequirements[0]?.id ?? "");
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [zoom, setZoom] = useState(96);
  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState(seedRequirements[0]?.normalizedText ?? "");
  const sourceRef = useRef<HTMLElement | null>(null);

  const selected = requirements.find((item) => item.id === selectedId) ?? requirements[0];

  const filtered = useMemo(() => {
    const lowered = query.trim().toLowerCase();
    return requirements.filter((item) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "review" && item.status !== "REVIEWED") ||
        (filter === "reviewed" && item.status === "REVIEWED");
      const matchesQuery =
        !lowered ||
        [item.id, item.clause, item.category, item.normalizedText]
          .join(" ")
          .toLowerCase()
          .includes(lowered);
      return matchesFilter && matchesQuery;
    });
  }, [filter, query, requirements]);

  const reviewQueue = useMemo(
    () => requirements.filter((item) => item.status !== "REVIEWED"),
    [requirements],
  );

  const reviewIndex = reviewQueue.findIndex((item) => item.id === selected?.id);

  useEffect(() => {
    if (!selected) return;
    setDraftText(selected.normalizedText);
    setEditing(false);
    const frame = window.requestAnimationFrame(() => {
      sourceRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [selectedId]);

  if (!selected) return null;

  function chooseRequirement(id: string) {
    setSelectedId(id);
  }

  function goReview(direction: number) {
    if (reviewQueue.length === 0) return;
    const current = reviewQueue.findIndex((item) => item.id === selected.id);
    const base = current >= 0 ? current : 0;
    const next = (base + direction + reviewQueue.length) % reviewQueue.length;
    const target = reviewQueue[next];
    if (target) setSelectedId(target.id);
  }

  function saveNormalizedText() {
    const nextText = draftText.trim();
    if (!nextText) return;
    setRequirements((current) =>
      current.map((item) =>
        item.id === selected.id ? { ...item, normalizedText: nextText } : item,
      ),
    );
    setEditing(false);
  }

  function markReviewed() {
    setRequirements((current) =>
      current.map((item) =>
        item.id === selected.id ? { ...item, status: "REVIEWED" as const } : item,
      ),
    );
  }

  function reopenReview() {
    setRequirements((current) =>
      current.map((item) =>
        item.id === selected.id ? { ...item, status: "UNREVIEWED" as const } : item,
      ),
    );
  }

  function updateNote(note: string) {
    setRequirements((current) =>
      current.map((item) => (item.id === selected.id ? { ...item, note } : item)),
    );
  }

  return (
    <div className="project-workspace">
      <header className="project-topbar">
        <div className="project-breadcrumbs">
          <Link href="/" className="breadcrumb-back" aria-label="Back to projects">
            <ArrowLeft size={15} aria-hidden="true" />
          </Link>
          <span className="breadcrumb-muted">Projects</span>
          <span className="breadcrumb-separator">/</span>
          <strong>Railway signalling system</strong>
          <span className="project-id">TND-2026-0142</span>
        </div>

        <div className="project-topbar-actions">
          <span className="saved-state">
            <Check size={13} aria-hidden="true" />
            Demo state
          </span>
          <button className="icon-button" type="button" aria-label="Project options">
            <MoreHorizontal size={17} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="project-tabs" role="tablist" aria-label="Project sections">
        <button className="project-tab project-tab-active" role="tab" aria-selected="true" type="button">
          Requirements
          <span>{requirements.length}</span>
        </button>
        <button className="project-tab" role="tab" aria-selected="false" type="button" disabled>
          Documents
          <span>3</span>
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
                ? String(reviewIndex + 1) + " of " + reviewQueue.length
                : "— of " + reviewQueue.length}
          </strong>
          <button type="button" onClick={() => goReview(-1)} disabled={reviewQueue.length === 0} aria-label="Previous requirement needing review">
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <button type="button" onClick={() => goReview(1)} disabled={reviewQueue.length === 0} aria-label="Next requirement needing review">
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="review-layout">
        <section className="requirements-pane" aria-label="Requirements">
          <div className="pane-heading">
            <div>
              <h1>Requirements</h1>
              <p>{requirements.length} extracted · source linked</p>
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
            <button
              className={filter === "all" ? "filter-tab filter-tab-active" : "filter-tab"}
              type="button"
              onClick={() => setFilter("all")}
            >
              All
            </button>
            <button
              className={filter === "review" ? "filter-tab filter-tab-active" : "filter-tab"}
              type="button"
              onClick={() => setFilter("review")}
            >
              Needs review
              <span>{reviewQueue.length}</span>
            </button>
            <button
              className={filter === "reviewed" ? "filter-tab filter-tab-active" : "filter-tab"}
              type="button"
              onClick={() => setFilter("reviewed")}
            >
              Reviewed
            </button>
          </div>

          <div className="requirement-list">
            {filtered.map((item) => {
              const active = item.id === selected.id;
              return (
                <article
                  key={item.id}
                  className={active ? "requirement-card requirement-card-active" : "requirement-card"}
                >
                  <button
                    type="button"
                    className="requirement-card-main"
                    onClick={() => chooseRequirement(item.id)}
                    aria-pressed={active}
                  >
                    <div className="requirement-meta-line">
                      <span>{item.id}</span>
                      <span>Clause {item.clause}</span>
                      {item.mandatory ? <span>Mandatory</span> : null}
                    </div>
                    <p>{item.normalizedText}</p>
                    <div className="requirement-card-bottom">
                      <span className={statusClass(item.status)}>
                        {item.status === "REVIEWED" ? <Check size={11} aria-hidden="true" /> : null}
                        {item.status === "OCR_WARNING" ? <CircleAlert size={11} aria-hidden="true" /> : null}
                        {item.status === "NEEDS_CLARIFICATION" ? <TriangleAlert size={11} aria-hidden="true" /> : null}
                        {statusLabel(item.status)}
                      </span>
                      <span className="requirement-category">{item.category}</span>
                    </div>
                  </button>

                  <span className="citation-wrap">
                    <button
                      type="button"
                      className="citation-chip"
                      onClick={() => chooseRequirement(item.id)}
                      aria-label={"Open source on page " + item.page}
                    >
                      <FileText size={12} aria-hidden="true" />
                      Tender.pdf · p.{item.page}
                    </button>
                    <span className="citation-glance" role="tooltip">
                      <span className="citation-glance-label">Source evidence</span>
                      <strong>Technical Tender v1</strong>
                      <p>{item.sourceText}</p>
                      <small>Page {item.page} · Clause {item.clause} · {item.locationPrecision} anchor</small>
                    </span>
                  </span>
                </article>
              );
            })}

            {filtered.length === 0 ? (
              <div className="empty-list">
                <Search size={18} aria-hidden="true" />
                <strong>No matching requirements</strong>
                <span>Try another search or filter.</span>
              </div>
            ) : null}
          </div>
        </section>

        <section className="source-pane" aria-label="Tender source document">
          <div className="source-toolbar">
            <div className="source-file">
              <span className="pdf-glyph">PDF</span>
              <div>
                <strong>Technical Tender v1.pdf</strong>
                <span>Original source document</span>
              </div>
            </div>

            <div className="source-toolbar-controls">
              <span className="page-indicator">Page {selected.page} of 26</span>
              <span className="toolbar-divider" />
              <button type="button" onClick={() => setZoom((value) => Math.max(80, value - 8))} aria-label="Zoom out">
                <Minus size={14} aria-hidden="true" />
              </button>
              <span className="zoom-value">{zoom}%</span>
              <button type="button" onClick={() => setZoom((value) => Math.min(128, value + 8))} aria-label="Zoom in">
                <Plus size={14} aria-hidden="true" />
              </button>
            </div>
          </div>

          <div className="source-stage">
            <article
              className="source-page"
              style={{
                transform: "scale(" + zoom / 100 + ")",
                transformOrigin: "top center",
              }}
            >
              <div className="source-page-header">
                <div>
                  <span>Technical specifications</span>
                  <strong>Section 4 — System requirements</strong>
                </div>
                <span>{selected.page}</span>
              </div>

              <div className="source-page-body">
                <p className="source-clause">Clause {selected.clause}</p>
                <h2>{selected.category} requirements</h2>
                <p>{selected.contextBefore}</p>

                <div className="source-finding">
                  <span className="finding-rule" aria-hidden="true" />
                  <mark ref={sourceRef}>{selected.sourceText}</mark>
                  <span className="source-anchor-label">
                    <Sparkles size={11} aria-hidden="true" />
                    Extracted as {selected.id}
                  </span>
                </div>

                <p>{selected.contextAfter}</p>

                <div className="source-spec-block" aria-hidden="true">
                  <div><span>Parameter</span><span>Requirement</span></div>
                  <div><span>Applicable section</span><span>{selected.clause}</span></div>
                  <div><span>Requirement class</span><span>{selected.category}</span></div>
                  <div><span>Bidder evidence</span><span>To be provided with technical offer</span></div>
                </div>

                <p>
                  Where a value or unit is specified, the value shall be reproduced exactly in the compliance matrix.
                  Ambiguous or unreadable source text shall be referred for review rather than inferred.
                </p>
              </div>

              <div className="source-page-footer">
                <span>Technical Tender v1</span>
                <span>Page {selected.page}</span>
              </div>
            </article>
          </div>
        </section>

        <aside className="evidence-pane" aria-label="Requirement evidence and review">
          <div className="evidence-header">
            <div>
              <p className="eyebrow">Review</p>
              <h2>Requirement evidence</h2>
            </div>
            <span className={statusClass(selected.status)}>{statusLabel(selected.status)}</span>
          </div>

          <div className="evidence-scroll">
            {selected.status === "OCR_WARNING" ? (
              <div className="review-alert">
                <CircleAlert size={16} aria-hidden="true" />
                <div>
                  <strong>OCR requires review</strong>
                  <p>The source anchor is approximate. Confirm the symbol and unit against the rendered page before approving.</p>
                </div>
              </div>
            ) : null}

            <section className="evidence-section">
              <div className="evidence-section-heading">
                <span>Source anchor</span>
                <span className="precision-pill">{selected.locationPrecision}</span>
              </div>

              <div className="source-reference">
                <span className="pdf-glyph">PDF</span>
                <div>
                  <strong>Technical Tender v1.pdf</strong>
                  <p>Page {selected.page} · Clause {selected.clause}</p>
                </div>
              </div>

              <blockquote>{selected.sourceText}</blockquote>
              <button
                type="button"
                className="text-action"
                onClick={() => sourceRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}
              >
                <Highlighter size={13} aria-hidden="true" />
                Locate in source
              </button>
            </section>

            <section className="evidence-section">
              <div className="evidence-section-heading">
                <span>Normalized requirement</span>
                {!editing ? (
                  <button type="button" className="tiny-action" onClick={() => setEditing(true)}>
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
                    <button type="button" className="button button-secondary button-small" onClick={() => { setDraftText(selected.normalizedText); setEditing(false); }}>
                      Cancel
                    </button>
                    <button type="button" className="button button-primary button-small" onClick={saveNormalizedText} disabled={!draftText.trim()}>
                      Save change
                    </button>
                  </div>
                </>
              ) : (
                <div className="normalized-card">
                  <span className="normalized-id">{selected.id}</span>
                  <p>{selected.normalizedText}</p>
                </div>
              )}

              <dl className="requirement-facts">
                <div><dt>Category</dt><dd>{selected.category}</dd></div>
                <div><dt>Mandatory</dt><dd>{selected.mandatory ? "Yes" : "Not explicit"}</dd></div>
                <div><dt>Source</dt><dd>Page {selected.page}</dd></div>
              </dl>
            </section>

            <section className="evidence-section">
              <div className="evidence-section-heading">
                <span>Reviewer note</span>
              </div>
              <textarea
                className="review-textarea note-textarea"
                value={selected.note}
                onChange={(event) => updateNote(event.target.value)}
                rows={4}
                placeholder="Add a note about wording, OCR, or source interpretation…"
                aria-label="Reviewer note"
              />
              <p className="field-help">Demo state only. Persistence lands with the requirement API.</p>
            </section>
          </div>

          <div className="evidence-footer">
            {selected.status === "REVIEWED" ? (
              <>
                <span className="reviewed-message"><Check size={14} aria-hidden="true" /> Reviewed</span>
                <button type="button" className="button button-secondary" onClick={reopenReview}>Reopen</button>
              </>
            ) : (
              <>
                <span className="footer-hint">Confirm wording against the highlighted source.</span>
                <button type="button" className="button button-primary" onClick={markReviewed}>
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
