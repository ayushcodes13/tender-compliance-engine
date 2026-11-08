"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  getPdfDocumentCacheKey,
  getCachedPdfDocument,
  setCachedPdfDocument,
  calculateTargetScrollTop,
  getVisiblePageFromOffsets,
} from "@/app/pdf-viewer-cache";

type Box = { x: number; y: number; width: number; height: number };
type ImageRegion = { id: string; bbox: Box; areaRatio: number };

interface PdfPageItemProps {
  pageNumber: number;
  pdfDocument: any;
  isTargetPage: boolean;
  selectedBox: Box | null;
  imageRegions: ImageRegion[];
  highlightLabel: string;
  displayScale: number;
  baseWidth: number;
  baseHeight: number;
  pixelRatio: number;
  onPageIntersect?: (pageNumber: number) => void;
}

function PdfPageItem({
  pageNumber,
  pdfDocument,
  isTargetPage,
  selectedBox,
  imageRegions,
  highlightLabel,
  displayScale,
  baseWidth,
  baseHeight,
  pixelRatio,
  onPageIntersect,
}: PdfPageItemProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [rendered, setRendered] = useState(false);
  const [isNearViewport, setIsNearViewport] = useState(false);
  const renderTaskRef = useRef<{ cancel: () => void; promise: Promise<void> } | null>(null);

  // Monitor visibility of this page element in viewport
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setIsNearViewport(true);
            if (entry.intersectionRatio > 0.45 && onPageIntersect) {
              onPageIntersect(pageNumber);
            }
          }
        }
      },
      {
        rootMargin: "450px 0px 450px 0px",
        threshold: [0, 0.5, 1.0],
      }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [pageNumber, onPageIntersect]);

  // Render page when it comes near viewport (or if it is the target page)
  useEffect(() => {
    if (!isNearViewport && !isTargetPage) return;
    if (!pdfDocument || !canvasRef.current) return;

    let cancelled = false;

    async function renderCanvas() {
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
      }
      try {
        const page = await pdfDocument.getPage(pageNumber);
        if (cancelled || !canvasRef.current) return;

        const viewport = page.getViewport({ scale: displayScale });
        const canvas = canvasRef.current;
        const context = canvas.getContext("2d");
        if (!context) return;

        canvas.width = Math.floor(viewport.width * pixelRatio);
        canvas.height = Math.floor(viewport.height * pixelRatio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;

        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);

        const task = page.render({ canvasContext: context, viewport });
        renderTaskRef.current = task;
        await task.promise;
        if (!cancelled) {
          setRendered(true);
        }
      } catch (err) {
        if (!cancelled && !(err instanceof Error && err.name === "RenderingCancelledException")) {
          // Render error silently handled; placeholder remains
        }
      }
    }

    void renderCanvas();

    return () => {
      cancelled = true;
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
      }
    };
  }, [pdfDocument, pageNumber, displayScale, pixelRatio, isNearViewport, isTargetPage]);

  const targetWidth = Math.floor(baseWidth * displayScale);
  const targetHeight = Math.floor(baseHeight * displayScale);

  return (
    <div
      ref={containerRef}
      id={`mvp-pdf-page-${pageNumber}`}
      className={`mvp-pdf-page ${isTargetPage ? "is-target-page" : ""}`}
      style={{
        width: `${targetWidth}px`,
        minHeight: `${targetHeight}px`,
      }}
    >
      <span className="mvp-pdf-page-badge">
        Page {pageNumber} {isTargetPage ? "· Cited source" : ""}
      </span>
      <canvas
        ref={canvasRef}
        aria-label={`PDF page ${pageNumber}`}
        style={{
          width: `${targetWidth}px`,
          height: `${targetHeight}px`,
          opacity: rendered ? 1 : 0.4,
          transition: "opacity 140ms ease",
        }}
      />
      {isTargetPage &&
        imageRegions.map((region) => (
          <div
            key={region.id}
            className="mvp-pdf-image-region"
            aria-label={`Approximate raster image region, ${Math.round(region.areaRatio * 100)} percent of page`}
            style={{
              left: `${region.bbox.x}%`,
              top: `${region.bbox.y}%`,
              width: `${region.bbox.width}%`,
              height: `${region.bbox.height}%`,
            }}
          />
        ))}
      {isTargetPage && selectedBox && (
        <div
          className="mvp-pdf-highlight"
          aria-label={highlightLabel}
          style={{
            left: `${selectedBox.x}%`,
            top: `${selectedBox.y}%`,
            width: `${selectedBox.width}%`,
            height: `${selectedBox.height}%`,
          }}
        />
      )}
    </div>
  );
}

export function PdfEvidenceViewer({
  file,
  pageNumber,
  selectedBox,
  imageRegions = [],
  highlightLabel = "Bounding box for cited source quote",
  onPageChange,
}: {
  file: File;
  pageNumber: number;
  selectedBox: Box | null;
  imageRegions?: ImageRegion[];
  highlightLabel?: string;
  onPageChange?: (activePage: number) => void;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("Loading document…");
  const [scale, setScale] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [baseDimensions, setBaseDimensions] = useState({ width: 595, height: 842 });
  const isAutoScrollingRef = useRef(false);
  const lastTargetPageRef = useRef<number | null>(null);

  // Load document with caching
  useEffect(() => {
    let cancelled = false;
    const cacheKey = getPdfDocumentCacheKey(file);

    async function loadPdf() {
      setStatus("Loading document pages…");
      try {
        let docPromise = getCachedPdfDocument(cacheKey);

        if (!docPromise) {
          const pdfjs = await import("pdfjs-dist");
          pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
          const bytes = new Uint8Array(await file.arrayBuffer());
          if (cancelled) return;

          const loading = pdfjs.getDocument({ data: bytes, isEvalSupported: false });
          docPromise = loading.promise;
          setCachedPdfDocument(cacheKey, docPromise);
        }

        const loadedDoc = await docPromise;
        if (cancelled) return;

        setPdfDoc(loadedDoc);
        setPageCount(loadedDoc.numPages || 1);

        // Sample page 1 for dimensions
        try {
          const firstPage = await loadedDoc.getPage(1);
          const viewport = firstPage.getViewport({ scale: 1 });
          setBaseDimensions({ width: viewport.width, height: viewport.height });
        } catch {
          // Use default A4 dimensions
        }

        setStatus("");
      } catch (err) {
        if (!cancelled) {
          setStatus("Could not load PDF document.");
        }
      }
    }

    void loadPdf();

    return () => {
      cancelled = true;
    };
  }, [file]);

  // Update scale on resize
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || !baseDimensions.width) return;

    function updateScale() {
      if (!stage) return;
      const availableWidth = Math.max(280, stage.clientWidth - 56);
      const displayScale = Math.min(1.35, availableWidth / baseDimensions.width);
      setScale(displayScale);
    }

    updateScale();
    const observer = new ResizeObserver(updateScale);
    observer.observe(stage);

    return () => observer.disconnect();
  }, [baseDimensions.width]);

  // Jump / auto-scroll to the target page and citation highlight
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || status || !pdfDoc) return;

    const targetEl = document.getElementById(`mvp-pdf-page-${pageNumber}`);
    if (!targetEl) return;

    isAutoScrollingRef.current = true;
    lastTargetPageRef.current = pageNumber;

    const pageHeight = targetEl.clientHeight || baseDimensions.height * scale;
    const targetScrollTop = calculateTargetScrollTop(
      targetEl.offsetTop,
      pageHeight,
      selectedBox,
      stage.clientHeight
    );

    stage.scrollTo({
      top: targetScrollTop,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });

    const timer = setTimeout(() => {
      isAutoScrollingRef.current = false;
    }, 450);

    return () => clearTimeout(timer);
  }, [pageNumber, selectedBox, scale, status, pdfDoc, baseDimensions.height]);

  // Handle page scrolling updates
  const handleScroll = useCallback(() => {
    if (isAutoScrollingRef.current || !stageRef.current || !onPageChange || pageCount <= 1) return;

    const stage = stageRef.current;
    const pageTops: Array<{ pageNumber: number; top: number; bottom: number }> = [];

    for (let p = 1; p <= pageCount; p++) {
      const el = document.getElementById(`mvp-pdf-page-${p}`);
      if (el) {
        pageTops.push({
          pageNumber: p,
          top: el.offsetTop,
          bottom: el.offsetTop + el.clientHeight,
        });
      }
    }

    if (pageTops.length > 0) {
      const visible = getVisiblePageFromOffsets(pageTops, stage.scrollTop, stage.clientHeight);
      if (visible !== lastTargetPageRef.current) {
        lastTargetPageRef.current = visible;
        onPageChange(visible);
      }
    }
  }, [pageCount, onPageChange]);

  const pixelRatio = typeof window !== "undefined" ? Math.min(window.devicePixelRatio || 1, 2) : 1;
  const pageNumbers = Array.from({ length: pageCount }, (_, i) => i + 1);

  return (
    <div className="mvp-pdf-stage" ref={stageRef} onScroll={handleScroll}>
      {status && (
        <div className="mvp-pdf-status" role="status">
          {status}
        </div>
      )}
      <div className="mvp-pdf-pages-list" style={{ visibility: status ? "hidden" : "visible" }}>
        {pdfDoc &&
          pageNumbers.map((p) => (
            <PdfPageItem
              key={p}
              pageNumber={p}
              pdfDocument={pdfDoc}
              isTargetPage={p === pageNumber}
              selectedBox={p === pageNumber ? selectedBox : null}
              imageRegions={p === pageNumber ? imageRegions : []}
              highlightLabel={highlightLabel}
              displayScale={scale}
              baseWidth={baseDimensions.width}
              baseHeight={baseDimensions.height}
              pixelRatio={pixelRatio}
            />
          ))}
      </div>
      {!status && <span className="mvp-pdf-zoom">Source view · {Math.round(scale * 100)}%</span>}
    </div>
  );
}
