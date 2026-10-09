"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileText, X } from "lucide-react";

import { SourceViewer } from "@/components/source-viewer";
import { api, SourceAnchor } from "@/lib/api/client";

export type CitationTarget = {
  projectId: string;
  documentId: string;
  documentName: string;
  version: number;
  pageNumber: number;
  requirementId?: string | null;
  sourceId?: string | null;
  quoteText?: string | null;
  clause?: string | null;
};

export function CitationEvidenceDrawer({
  citation,
  onClose,
}: {
  citation: CitationTarget | null;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [anchor, setAnchor] = useState<SourceAnchor | null>(null);
  const [anchorLoading, setAnchorLoading] = useState(false);

  useEffect(() => {
    if (!citation) return;
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, [citation]);

  useEffect(() => {
    if (!citation) return;
    let cancelled = false;
    setAnchor(null);
    setAnchorLoading(true);
    api
      .fetchPageSources(
        citation.projectId,
        citation.documentId,
        citation.version,
        citation.pageNumber,
        citation.quoteText ?? undefined
      )
      .then((sources) => {
        if (cancelled) return;
        const selected = citation.sourceId
          ? sources.find((source) => source.anchor_id === citation.sourceId)
          : sources.find(
              (source) =>
                source.quote_text &&
                source.quote_text.replace(/\s+/g, " ").trim() ===
                  citation.quoteText?.replace(/\s+/g, " ").trim()
            );
        setAnchor(selected ?? null);
      })
      .catch(() => {
        if (!cancelled) setAnchor(null);
      })
      .finally(() => {
        if (!cancelled) setAnchorLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [citation]);

  if (!citation) return null;

  const quote = anchor?.quote_text ?? citation.quoteText ?? "";
  const precision = anchor?.location_type;

  return (
    <dialog
      ref={dialogRef}
      className="citation-evidence-dialog"
      aria-labelledby="citation-evidence-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) onClose();
      }}
    >
      <div className="citation-evidence-backdrop" aria-hidden="true" />
      <section className="citation-evidence-panel" aria-label="Citation evidence">
        <header className="citation-evidence-header">
          <div className="citation-evidence-heading">
            <span className="citation-evidence-kicker">Source evidence</span>
            <h2 id="citation-evidence-title">Evidence</h2>
          </div>
          <button
            type="button"
            className="citation-evidence-close"
            onClick={onClose}
            aria-label="Close evidence panel"
            autoFocus
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="citation-evidence-body">
          <aside className="citation-evidence-context" aria-label="Selected citation details">
            <div className="citation-evidence-document">
              <FileText size={16} aria-hidden="true" />
              <span title={citation.documentName}>{citation.documentName}</span>
            </div>
            <div className="citation-evidence-meta">
              <span>Page {citation.pageNumber}</span>
              <span>Version {citation.version}</span>
              {citation.clause ? <span>Clause {citation.clause}</span> : null}
            </div>
            <div className="citation-evidence-precision">
              {precision === "exact" ? (
                <CheckCircle2 size={14} aria-hidden="true" />
              ) : null}
              <span>
                {anchorLoading
                  ? "Checking saved source location…"
                  : precision === "exact"
                    ? "Exact source anchor"
                    : precision === "approximate"
                      ? "Approximate source anchor"
                      : "Source location not confirmed"}
              </span>
            </div>
            {quote ? (
              <blockquote className="citation-evidence-quote">
                <span>Quoted source text</span>
                <mark>{quote}</mark>
              </blockquote>
            ) : (
              <div className="citation-evidence-empty" role="status">
                The saved citation excerpt is unavailable. The immutable source
                page is shown so you can inspect it directly.
              </div>
            )}
            <p className="citation-evidence-note">
              The page highlight reflects the saved anchor. Approximate anchors
              remain labeled as approximate.
            </p>
          </aside>

          <div className="citation-evidence-page">
            <SourceViewer
              projectId={citation.projectId}
              documentId={citation.documentId}
              documentName={citation.documentName}
              version={citation.version}
              pageNumber={citation.pageNumber}
              selectedRequirementId={citation.requirementId ?? null}
              selectedAnchorId={citation.sourceId ?? null}
              highlightQuote={anchor?.quote_text ?? citation.quoteText ?? null}
              className="citation-evidence-source-viewer"
            />
          </div>
        </div>
      </section>
    </dialog>
  );
}
