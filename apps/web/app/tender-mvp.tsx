"use client";

import { useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowRight, Check, FileText, LoaderCircle, Upload, X } from "lucide-react";
import { PdfEvidenceViewer } from "@/components/mvp/pdf-evidence-viewer";
import { analyzeTender } from "./actions";

type BoundingBox = { x: number; y: number; width: number; height: number };
type Requirement = {
  id: string;
  text: string;
  category: string;
  page: number;
  quote: string;
  bbox: BoundingBox | null;
  precision: "exact" | "page-only";
  reviewed: boolean;
};
type Analysis = {
  filename: string;
  pageCount: number;
  textPages: number;
  requirements: Requirement[];
  rejectedCandidates: number;
  reviewNote: string;
};

export default function TenderMvpPage() {
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const active = useMemo(
    () => analysis?.requirements.find((item) => item.id === activeId) ?? analysis?.requirements[0] ?? null,
    [analysis, activeId],
  );

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    setError(null);
    setAnalysis(null);
    setActiveId(null);
    setFile(event.target.files?.[0] ?? null);
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.set("file", file);
    try {
      const result = await analyzeTender(body);
      if (!result.ok) throw new Error(result.error);
      const payload = result.analysis as Analysis;
      setAnalysis(payload);
      setActiveId(payload.requirements[0]?.id ?? null);
      setPage(payload.requirements[0]?.page ?? 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The tender could not be processed.");
    } finally {
      setBusy(false);
    }
  }

  function openRequirement(item: Requirement) {
    setActiveId(item.id);
    setPage(item.page);
  }

  function markReviewed() {
    if (!analysis || !active) return;
    setAnalysis({
      ...analysis,
      requirements: analysis.requirements.map((item) => item.id === active.id ? { ...item, reviewed: !item.reviewed } : item),
    });
  }

  async function exportDocx() {
    if (!analysis) return;
    setExporting(true);
    setError(null);
    try {
      const { Document, HeadingLevel, Packer, Paragraph, Table, TableCell, TableRow, TextRun, WidthType } = await import("docx");
      const cell = (text: string, bold = false) => new TableCell({
        children: [new Paragraph({ children: [new TextRun({ text, bold })] })],
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
      });
      const rows = [
        new TableRow({ tableHeader: true, children: [cell("Tender requirement", true), cell("OEM response", true), cell("Source", true)] }),
        ...analysis.requirements.map((item) => new TableRow({
          cantSplit: true,
          children: [cell(item.text), cell(""), cell(`Page ${item.page}`)],
        })),
      ];
      const doc = new Document({
        sections: [{
          properties: {},
          children: [
            new Paragraph({ text: "Tender Technical Requirements", heading: HeadingLevel.TITLE }),
            new Paragraph({ text: `Source tender: ${analysis.filename}` }),
            new Paragraph({ text: `${analysis.requirements.length} source-matched requirements · ${analysis.requirements.filter((item) => item.reviewed).length} checked by reviewer` }),
            new Paragraph({ text: "AI-assisted draft for human review. This document does not guarantee tender completeness." }),
            new Table({ rows, width: { size: 100, type: WidthType.PERCENTAGE }, columnWidths: [5800, 2300, 1200] }),
          ],
        }],
      });
      const blob = await Packer.toBlob(doc);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${analysis.filename.replace(/\.pdf$/i, "")}-technical-response.docx`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
    } catch {
      setError("The response sheet could not be created. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  if (!analysis) {
    return (
      <main className="tender-mvp-root">
        <header className="mvp-topbar">
          <a className="mvp-brand" href="/" aria-label="Tender Compliance home"><span className="mvp-brand-mark">T</span><span>Tender Review</span></a>
          <span className="mvp-private"><span /> Single-user demo</span>
        </header>
        <section className="mvp-upload-wrap">
          <div className="mvp-eyebrow">SOURCE-VERIFIED AI WORKFLOW</div>
          <h1>Turn a tender into a reviewable response sheet.</h1>
          <p className="mvp-lede">Upload a text-based tender PDF. AI drafts technical requirements, checks each quote against its cited page, and opens the evidence beside the text.</p>
          <form className="mvp-upload-card" onSubmit={analyze}>
            <label className={`mvp-dropzone ${file ? "is-ready" : ""}`} htmlFor="tender-file">
              <input id="tender-file" type="file" accept="application/pdf,.pdf" onChange={selectFile} />
              <span className="mvp-upload-icon"><Upload size={21} /></span>
              {file ? <><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · ready to review</span></> : <><strong>Choose a tender PDF</strong><span>Text-based PDF · up to 4 MB · up to 120 pages</span></>}
            </label>
            <button className="mvp-primary" type="submit" disabled={!file || busy}>
              {busy ? <><LoaderCircle className="mvp-spin" size={17} /> Reading and checking sources…</> : <>Extract requirements <ArrowRight size={17} /></>}
            </button>
            {error && <p className="mvp-error" role="alert">{error}</p>}
          </form>
          <div className="mvp-trust-row"><span><Check size={14} /> Literal source quote required</span><span><Check size={14} /> Page-level bounding boxes</span><span><Check size={14} /> OEM response fields stay blank</span></div>
          <p className="mvp-footnote">Scanned PDFs need OCR and are not supported in this MVP. All extracted items remain unreviewed until a person checks them.</p>
        </section>
      </main>
    );
  }

  const checkedCount = analysis.requirements.filter((item) => item.reviewed).length;
  return (
    <main className="tender-mvp-root">
      <header className="mvp-topbar">
        <a className="mvp-brand" href="/" aria-label="Start a new tender"><span className="mvp-brand-mark">T</span><span>Tender Review</span></a>
        <div className="mvp-topbar-right"><span className="mvp-file-name"><FileText size={15} />{analysis.filename}</span><span className="mvp-private"><span /> Single-user demo</span></div>
      </header>
      <div className="mvp-workspace">
        <section className="mvp-list-panel" aria-label="Extracted requirements">
          <div className="mvp-panel-heading"><div><div className="mvp-eyebrow">TECHNICAL REVIEW</div><h1>Requirements</h1></div><button className="mvp-text-button" onClick={() => { setAnalysis(null); setFile(null); setError(null); }}><X size={15} /> New tender</button></div>
          <div className="mvp-summary"><span>{analysis.requirements.length} source-matched</span><span>{checkedCount} checked</span><span>{analysis.pageCount} pages</span></div>
          <p className="mvp-review-note">{analysis.reviewNote} {analysis.rejectedCandidates ? `${analysis.rejectedCandidates} unmatched model suggestions were left out.` : "Unmatched suggestions are left out."}</p>
          <div className="mvp-requirement-list">
            {analysis.requirements.map((item, index) => (
              <button className={`mvp-requirement ${active?.id === item.id ? "is-active" : ""}`} key={item.id} onClick={() => openRequirement(item)}>
                <span className="mvp-req-topline"><span>REQ {String(index + 1).padStart(3, "0")}</span><span className="mvp-citation-tag">Page {item.page} · exact</span></span>
                <span className="mvp-req-text">{item.text}</span>
                <span className="mvp-req-bottom"><span>{item.category}</span><span className={item.reviewed ? "mvp-reviewed" : "mvp-unreviewed"}>{item.reviewed ? "Checked" : "Needs review"}</span></span>
              </button>
            ))}
          </div>
          <div className="mvp-list-footer"><button className="mvp-export" onClick={exportDocx} disabled={exporting || analysis.requirements.length === 0}>{exporting ? <LoaderCircle className="mvp-spin" size={16} /> : <ArrowDownToLine size={16} />}{exporting ? "Building DOCX…" : "Download response sheet"}</button><p>DOCX includes source pages and blank OEM response cells.</p>{error && <p className="mvp-error" role="alert">{error}</p>}</div>
        </section>

        <section className="mvp-evidence-panel" aria-label="Cited tender source">
          <div className="mvp-evidence-heading"><div><div className="mvp-eyebrow">SOURCE EVIDENCE</div><h2>{active && active.page === page ? `Page ${page} citation` : `Page ${page} source`}</h2></div><div className="mvp-evidence-actions"><button className="mvp-icon-button" onClick={() => setPage((current) => Math.max(1, current - 1))} aria-label="Previous page" disabled={page <= 1}><ArrowLeft size={16} /></button><span>{page} / {analysis.pageCount}</span><button className="mvp-icon-button" onClick={() => setPage((current) => Math.min(analysis.pageCount, current + 1))} aria-label="Next page" disabled={page >= analysis.pageCount}><ArrowRight size={16} /></button></div></div>
          {file && <PdfEvidenceViewer file={file} pageNumber={page} selectedBox={active?.page === page ? active.bbox : null} />}
          <div className="mvp-citation-detail">
            <div className="mvp-citation-label"><span className="mvp-exact-dot" /> Exact source quote · page {active?.page ?? page}</div>
            <blockquote>{active?.quote ?? "Choose a requirement to inspect its tender source."}</blockquote>
            <div className="mvp-review-actions"><span>{active?.reviewed ? "You checked this citation against the page." : page === active?.page && active?.bbox ? "Confirm the wording and highlight against the original." : "Open the cited page to check the quote and highlight."}</span><button disabled={!active || page !== active.page || !active.bbox} className={active?.reviewed ? "mvp-check-button is-checked" : "mvp-check-button"} onClick={markReviewed}>{active?.reviewed ? <><Check size={14} /> Checked</> : "Mark checked"}</button></div>
          </div>
        </section>
      </div>
    </main>
  );
}
