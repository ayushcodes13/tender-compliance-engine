"use client";

import { useEffect, useRef, useState } from "react";

type Box = { x: number; y: number; width: number; height: number };

export function PdfEvidenceViewer({
  file,
  pageNumber,
  selectedBox,
}: {
  file: File;
  pageNumber: number;
  selectedBox: Box | null;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState("Loading tender page…");
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (!stage || !canvas) return;
    let cancelled = false;
    let generation = 0;
    let renderTask: { cancel: () => void; promise: Promise<void> } | undefined;
    let pdfDocument: { getPage: (page: number) => Promise<any>; destroy: () => Promise<void> } | undefined;

    async function renderPage() {
      const currentGeneration = ++generation;
      const previousRender = renderTask;
      previousRender?.cancel();
      try {
        await previousRender?.promise.catch(() => undefined);
        if (cancelled || currentGeneration !== generation || !pdfDocument) return;
        const page = await pdfDocument.getPage(pageNumber);
        if (cancelled || currentGeneration !== generation) return;
        const baseViewport = page.getViewport({ scale: 1 });
        const availableWidth = Math.max(240, stage!.clientWidth - 48);
        const displayScale = Math.min(1.35, availableWidth / baseViewport.width);
        const viewport = page.getViewport({ scale: displayScale });
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        const context = canvas!.getContext("2d");
        if (!context) throw new Error("Canvas rendering is unavailable.");
        canvas!.width = Math.floor(viewport.width * pixelRatio);
        canvas!.height = Math.floor(viewport.height * pixelRatio);
        canvas!.style.width = `${viewport.width}px`;
        canvas!.style.height = `${viewport.height}px`;
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
        const task = page.render({ canvasContext: context, viewport });
        renderTask = task;
        await task.promise;
        if (cancelled || currentGeneration !== generation) return;
        setScale(displayScale);
        setStatus("");
      } catch (error) {
        if (!cancelled && currentGeneration === generation && !(error instanceof Error && error.name === "RenderingCancelledException")) {
          setStatus("Could not render this PDF page.");
        }
      }
    }

    async function loadDocument() {
      setStatus("Loading tender page…");
      try {
        const pdfjs = await import("pdfjs-dist");
        // Serve the worker as a static asset: Next does not bundle PDF.js's
        // ESM worker URL correctly when referenced from a client component.
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        const bytes = new Uint8Array(await file.arrayBuffer());
        if (cancelled) return;
        const loading = pdfjs.getDocument({ data: bytes, isEvalSupported: false });
        pdfDocument = await loading.promise;
        if (cancelled) return;
        await renderPage();
      } catch (error) {
        if (!cancelled) setStatus("Could not render this PDF page.");
      }
    }

    void loadDocument();
    const observer = new ResizeObserver(() => {
      if (pdfDocument) void renderPage();
    });
    observer.observe(stage);

    return () => {
      cancelled = true;
      generation += 1;
      observer.disconnect();
      renderTask?.cancel();
      if (pdfDocument) void pdfDocument.destroy();
    };
  }, [file, pageNumber]);

  useEffect(() => {
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (!stage || !canvas || !selectedBox || !scale) return;
    const top = (selectedBox.y / 100) * Number.parseFloat(canvas.style.height || "0");
    stage.scrollTo({ top: Math.max(0, top - stage.clientHeight * 0.38), behavior: "smooth" });
  }, [selectedBox, scale]);

  return (
    <div className="mvp-pdf-stage" ref={stageRef}>
      {status && <div className="mvp-pdf-status" role="status">{status}</div>}
      <div className="mvp-pdf-page" style={{ visibility: status ? "hidden" : "visible" }}>
        <canvas ref={canvasRef} aria-label={`Tender PDF page ${pageNumber}`} />
        {selectedBox && (
          <div
            className="mvp-pdf-highlight"
            aria-label="Bounding box for cited source quote"
            style={{ left: `${selectedBox.x}%`, top: `${selectedBox.y}%`, width: `${selectedBox.width}%`, height: `${selectedBox.height}%` }}
          />
        )}
      </div>
      {!status && <span className="mvp-pdf-zoom">Source view · {Math.round(scale * 100)}%</span>}
    </div>
  );
}
