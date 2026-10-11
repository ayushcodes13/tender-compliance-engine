"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { ZoomIn, ZoomOut, RotateCw, ChevronLeft, ChevronRight } from "lucide-react";
import { api, PageResponse, SourceAnchor } from "@/lib/api/client";

export interface SourceViewerProps {
  projectId: string;
  documentId: string;
  documentName?: string;
  version: number;
  pageNumber: number;
  /** Called when the user navigates to a different page. */
  onPageChange?: (page: number) => void;
  /** Optional total page count for display. */
  totalPages?: number;
  /** Requirement whose source location was opened by a citation. */
  selectedRequirementId?: string | null;
  /** Persisted source anchor selected by a citation. */
  selectedAnchorId?: string | null;
  /** Exact excerpt opened from an obligation-coverage finding. */
  highlightQuote?: string | null;
  /** Optional class for the container. */
  className?: string;
}

function normalizeQuoteForSelection(value: string | null | undefined): string {
  return value?.replace(/\s+/g, " ").trim() ?? "";
}

/**
 * SourceViewer — renders a real uploaded source page (CP36).
 *
 * Fetches the rendered page PNG from the API and highlights the selected
 * citation's source anchor. Falls back to a text view when no rendered image
 * is available (explicit 404 from the backend); precision remains visible in
 * the review panel and is never upgraded here.
 */
export function SourceViewer({
  projectId,
  documentId,
  documentName,
  version,
  pageNumber,
  onPageChange,
  totalPages,
  selectedRequirementId = null,
  selectedAnchorId = null,
  highlightQuote = null,
  className = "",
}: SourceViewerProps) {
  const [page, setPage] = useState<PageResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [anchors, setAnchors] = useState<SourceAnchor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(100);
  const [imageScale, setImageScale] = useState(1);
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const selectedAnchorRef = useRef<HTMLDivElement>(null);

  const loadPage = useCallback(async () => {
    setLoading(true);
    setError(null);
    setImageUrl(null);
    setAnchors([]);

    try {
      const [pageData, anchorData] = await Promise.all([
        api
          .fetchPage(projectId, documentId, version, pageNumber)
          .catch(() => null),
        api
          .fetchPageSources(projectId, documentId, version, pageNumber, highlightQuote ?? undefined)
          .catch(() => []),
      ]);
      setPage(pageData);
      setAnchors(anchorData ?? []);

      if (pageData?.has_image) {
        api
          .fetchPageImage(projectId, documentId, version, pageNumber)
          .then((blob) => {
            setImageUrl(URL.createObjectURL(blob));
          })
          .catch((err) => {
            setError(`Failed to load page image: ${err.message}`);
          });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load page");
    } finally {
      setLoading(false);
    }
  }, [projectId, documentId, version, pageNumber, highlightQuote]);

  const isSelected = useCallback(
    (anchor: SourceAnchor) => {
      if (selectedAnchorId) return anchor.anchor_id === selectedAnchorId;
      return Boolean(
        (selectedRequirementId && anchor.requirement_id === selectedRequirementId) ||
          (highlightQuote &&
            normalizeQuoteForSelection(anchor.quote_text) ===
              normalizeQuoteForSelection(highlightQuote))
      );
    },
    [selectedRequirementId, selectedAnchorId, highlightQuote]
  );

  useEffect(() => {
    void loadPage();
    // Revoke object URL on page/number change to avoid memory leaks.
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadPage]);

  // Citation navigation can finish before the page image has rendered. Keep
  // the selected highlight centered once both the anchor and image geometry
  // are ready, including after a zoom change.
  useEffect(() => {
    if (!selectedAnchorId && !selectedRequirementId && !highlightQuote) return;
    const selectedAnchor = anchors.find(isSelected);
    if (!selectedAnchor) return;
    selectedAnchorRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "center",
      inline: "center",
    });
  }, [anchors, imageUrl, imageScale, isSelected, selectedAnchorId, zoom]);

  const handleZoomIn = () => setZoom((z) => Math.min(200, z + 8));
  const handleZoomOut = () => setZoom((z) => Math.max(50, z - 8));
  const handleResetZoom = () => setZoom(100);

  const handlePrevPage = () => {
    if (onPageChange && pageNumber > 1) onPageChange(pageNumber - 1);
  };
  const handleNextPage = () => {
    if (onPageChange && totalPages && pageNumber < totalPages)
      onPageChange(pageNumber + 1);
  };

  /**
   * Convert a bbox from the rendered image's coordinate space to the
   * displayed (zoomed) coordinate space.  The bbox values come from the
   * backend and are in the original page image dimensions.
   */
  const getBboxStyle = useCallback(
    (anchor: SourceAnchor) => {
      const bbox = anchor.bbox;
      if (!bbox) return null;
      return {
        left: `${bbox.x / imageScale}px`,
        top: `${bbox.y / imageScale}px`,
        width: `${bbox.width / imageScale}px`,
        height: `${bbox.height / imageScale}px`,
      };
    },
    [imageScale]
  );

  const handleImageLoad = () => {
    if (imgRef.current) {
      // imageScale = naturalWidth / displayedWidth
      const displayedWidth = containerRef.current
        ? containerRef.current.offsetWidth
        : imgRef.current.naturalWidth;
      setImageScale(imgRef.current.naturalWidth / displayedWidth);
    }
  };

  if (loading) {
    return (
      <div className={`source-pane ${className}`} aria-label="Source document">
        <div className="source-toolbar">
          <div className="source-file">
            <span className="pdf-glyph">PDF</span>
            <div>
              <strong>Loading page {pageNumber}…</strong>
              <span>Preparing source view</span>
            </div>
          </div>
        </div>
        <div className="source-stage">
          <div className="source-page-body">
            <div className="loading-shimmer" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`source-pane ${className}`} aria-label="Source document">
        <div className="source-toolbar">
          <div className="source-file">
            <span className="pdf-glyph">PDF</span>
            <div>
              <strong>Error loading page</strong>
              <span>{error}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Fallback: no rendered image available — show text-based view with
  // source anchors labeled as approximate.
  if (page && !page.has_image) {
    return (
      <div className={`source-pane ${className}`} aria-label="Source document">
        <div className="source-toolbar">
          <div className="source-file">
            <span className="pdf-glyph">PDF</span>
            <div>
              <strong>{documentName ?? `Technical Tender v${version}`}</strong>
              <span>
                Page {pageNumber}
                {totalPages ? ` of ${totalPages}` : ""} · No rendered image
              </span>
            </div>
          </div>
          <div className="source-toolbar-controls">
            {page.ocr_needed && (
              <span className="precision-pill status-warning">
                OCR text only
              </span>
            )}
          </div>
        </div>

        <div className="source-stage">
          <article className="source-page">
            <div className="source-page-header">
              <div>
                <span>Text-only fallback</span>
                <strong>Native text (no rendered image)</strong>
              </div>
              <span>{pageNumber}</span>
            </div>

            <div className="source-page-body">
              {selectedAnchorId &&
              !anchors.some((anchor) => anchor.anchor_id === selectedAnchorId) ? (
                <aside className="source-highlight-unavailable" role="status">
                  <strong>Selected citation could not be located</strong>
                  {highlightQuote ? <p><mark>{highlightQuote}</mark></p> : null}
                  <span>
                    The immutable page is open, but the saved source anchor is
                    unavailable. No other excerpt has been highlighted.
                  </span>
                </aside>
              ) : null}
              {anchors.map((anchor, index) => (
                <div
                  key={anchor.anchor_id ?? anchor.requirement_id ?? `${anchor.quote_text ?? "source"}-${index}`}
                  ref={isSelected(anchor) ? selectedAnchorRef : null}
                  className={`source-finding ${isSelected(anchor) ? "selected" : ""}`}
                >
                  <span
                    className="finding-rule"
                    aria-hidden="true"
                  />
                  <mark>{anchor.quote_text ?? anchor.source_text ?? "(no source text)"}</mark>
                  <span className="source-anchor-label">
                    Clause {anchor.clause_number ?? "?"} ·{" "}
                    {anchor.location_type === "exact"
                      ? "Exact"
                      : "Approximate"}
                  </span>
                </div>
              ))}

              {page.cleaned_text && (
                <div className="source-text-fallback">
                  {page.cleaned_text}
                </div>
              )}
            </div>

            <div className="source-page-footer">
              <span>{documentName ?? `Technical Tender v${version}`}</span>
              <span>Page {pageNumber}</span>
            </div>
          </article>
        </div>
      </div>
    );
  }

  // Full image viewer with overlay.
  return (
    <div className={`source-pane ${className}`} aria-label="Source document">
      <div className="source-toolbar">
        <div className="source-file">
          <span className="pdf-glyph">PDF</span>
          <div>
            <strong>{documentName ?? `Technical Tender v${version}`}</strong>
            <span>
              Page {pageNumber}
              {totalPages ? ` of ${totalPages}` : ""}
              {page?.ocr_confidence != null
                ? ` · OCR ${Math.round(page.ocr_confidence * 100)}%`
                : ""}
            </span>
          </div>
        </div>

        <div className="source-toolbar-controls">
          {onPageChange && (
            <>
              <button
                type="button"
                onClick={handlePrevPage}
                disabled={pageNumber <= 1}
                aria-label="Previous page"
              >
                <ChevronLeft size={14} aria-hidden="true" />
              </button>
              <span className="page-indicator">
                {pageNumber}
                {totalPages ? ` / ${totalPages}` : ""}
              </span>
              <button
                type="button"
                onClick={handleNextPage}
                disabled={!totalPages || pageNumber >= totalPages}
                aria-label="Next page"
              >
                <ChevronRight size={14} aria-hidden="true" />
              </button>
              <span className="toolbar-divider" />
            </>
          )}

          <button
            type="button"
            onClick={handleZoomOut}
            aria-label="Zoom out"
          >
            <ZoomOut size={14} aria-hidden="true" />
          </button>
          <span className="zoom-value">{zoom}%</span>
          <button
            type="button"
            onClick={handleZoomIn}
            aria-label="Zoom in"
          >
            <ZoomIn size={14} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={handleResetZoom}
            aria-label="Reset zoom"
            className="tiny-action"
          >
            <RotateCw size={12} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="source-stage">
        {(() => {
          const selectedAnchor = anchors.find(isSelected);
          const displayedQuote = selectedAnchor?.quote_text ?? selectedAnchor?.source_text ?? highlightQuote;
          if (!displayedQuote || selectedAnchor?.bbox) {
            return null;
          }
          return (
            <aside
              ref={selectedAnchorRef}
              className="source-highlight-unavailable"
              role="status"
            >
              <strong>
                {!selectedAnchor
                  ? "Excerpt not located in page text"
                  : selectedAnchor.location_type === "exact"
                  ? "Exact text anchor · image highlight unavailable"
                  : "Approximate source anchor"}
              </strong>
              <p><mark>{displayedQuote}</mark></p>
              <span>
                {!selectedAnchor
                  ? "The page is open, but this excerpt was not found in its saved text. It has not been highlighted."
                  : "The page is open, but the system has no verified text-to-image box for this excerpt."}
              </span>
            </aside>
          );
        })()}
        <div
          ref={containerRef}
          className="source-image-container"
          style={{
            transform: `scale(${zoom / 100})`,
            transformOrigin: "top center",
          }}
        >
          {imageUrl ? (
            <img
              ref={imgRef}
              src={imageUrl}
              alt={`Page ${pageNumber} of ${documentName ?? `Technical Tender v${version}`}`}
              className="source-page-image"
              onLoad={handleImageLoad}
              draggable={false}
            />
          ) : (
            <div className="source-placeholder">
              Image unavailable, showing text fallback…
            </div>
          )}

          {/* Bounding-box overlay — only rendered when image is loaded and
              anchors have bbox data.  Each rectangle is positioned relative to
              the natural image dimensions; the container scale (zoom) is
              applied via CSS transform so coordinates stay proportional. */}
          {imageUrl &&
            anchors.filter(isSelected).map((anchor, index) => {
              const style = getBboxStyle(anchor);
              if (!style) return null;
              return (
                <div
                  key={anchor.anchor_id ?? anchor.requirement_id ?? `${anchor.quote_text ?? "source"}-${index}`}
                  ref={selectedAnchorRef}
                  className={`source-highlight ${anchor.location_type === "exact" ? "exact" : "approximate"} selected`}
                  style={style}
                  title={`${anchor.location_type === "exact" ? "Exact" : "Approximate"} source: ${anchor.quote_text ?? anchor.source_text ?? ""}`}
                >
                  <span className="source-highlight-label">
                    Cited source
                  </span>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
