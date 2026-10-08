"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { ZoomIn, ZoomOut, RotateCw, ChevronLeft, ChevronRight } from "lucide-react";
import { api, PageResponse, SourceAnchor } from "@/lib/api/client";

export interface SourceViewerProps {
  projectId: string;
  documentId: string;
  version: number;
  pageNumber: number;
  /** Called when the user navigates to a different page. */
  onPageChange?: (page: number) => void;
  /** Optional total page count for display. */
  totalPages?: number;
  /** Requirement whose source location was opened by a citation. */
  selectedRequirementId?: string | null;
  /** Optional class for the container. */
  className?: string;
}

/**
 * SourceViewer — renders a real uploaded source page (CP36).
 *
 * Fetches the rendered page PNG from the API and overlays source-anchor
 * bounding boxes from requirements.  Falls back to a text view when no
 * rendered image is available (explicit 404 from the backend), and
 * labels each anchor's location precision ("Exact" / "Approximate")
 * without upgrading certainty.
 */
export function SourceViewer({
  projectId,
  documentId,
  version,
  pageNumber,
  onPageChange,
  totalPages,
  selectedRequirementId = null,
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
          .fetchPageSources(projectId, documentId, version, pageNumber)
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
  }, [projectId, documentId, version, pageNumber]);

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
    if (!selectedRequirementId) return;
    const selectedAnchor = anchors.find(
      (anchor) => anchor.requirement_id === selectedRequirementId
    );
    if (!selectedAnchor) return;
    selectedAnchorRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "center",
      inline: "center",
    });
  }, [anchors, imageUrl, imageScale, selectedRequirementId, zoom]);

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
              <strong>Technical Tender v{version}</strong>
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
              {anchors.map((anchor) => (
                <div
                  key={anchor.requirement_id}
                  ref={anchor.requirement_id === selectedRequirementId ? selectedAnchorRef : null}
                  className={`source-finding ${anchor.requirement_id === selectedRequirementId ? "selected" : ""}`}
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
              <span>Technical Tender v{version}</span>
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
            <strong>Technical Tender v{version}</strong>
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
          const selectedAnchor = anchors.find(
            (anchor) => anchor.requirement_id === selectedRequirementId
          );
          if (!selectedAnchor || selectedAnchor.bbox || !(selectedAnchor.quote_text ?? selectedAnchor.source_text)) {
            return null;
          }
          return (
            <aside
              ref={selectedAnchorRef}
              className="source-highlight-unavailable"
              role="status"
            >
              <strong>
                {selectedAnchor.location_type === "exact"
                  ? "Exact text anchor · image highlight unavailable"
                  : "Approximate source anchor"}
              </strong>
              <p><mark>{selectedAnchor.quote_text ?? selectedAnchor.source_text}</mark></p>
              <span>The page is open, but the system has no verified text-to-image box for this excerpt.</span>
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
              alt={`Page ${pageNumber} of Technical Tender v${version}`}
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
            anchors.map((anchor) => {
              const style = getBboxStyle(anchor);
              if (!style) return null;
              const selected = anchor.requirement_id === selectedRequirementId;
              return (
                <div
                  key={anchor.requirement_id}
                  ref={selected ? selectedAnchorRef : null}
                  className={`source-highlight ${anchor.location_type === "exact" ? "exact" : "approximate"} ${selected ? "selected" : ""}`}
                  style={style}
                  title={`${anchor.location_type === "exact" ? "Exact" : "Approximate"} source: ${anchor.quote_text ?? anchor.source_text ?? ""}`}
                >
                  <span className="source-highlight-label">
                    {anchor.clause_number ?? "?"}
                    {anchor.location_type === "exact" ? "Exact" : "Approx"}
                  </span>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
