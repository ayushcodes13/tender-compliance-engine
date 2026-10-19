"use client";

import { useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, Check, FileCheck2, FileText, LoaderCircle, ScanSearch, ShieldCheck, Upload, X } from "lucide-react";
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
      <main className="tender-mvp-root mvp-landing">
        <header className="mvp-topbar mvp-landing-topbar">
          <a className="mvp-brand" href="#top" aria-label="Tender Review home"><span className="mvp-brand-mark">T</span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Technical response workspace</small></span></a>
          <nav className="mvp-landing-nav" aria-label="Main navigation"><a href="#how-it-works">How it works</a><a href="#evidence">Source evidence</a></nav>
          <a className="mvp-topbar-cta" href="#upload">Start a review <ArrowUpRight size={15} /></a>
        </header>
        <section className="mvp-landing-hero" id="top">
          <div className="mvp-hero-copy">
            <div className="mvp-eyebrow"><span className="mvp-eyebrow-mark" /> TENDER REVIEW WORKSPACE</div>
            <h1>Every requirement.<br /><em>Right back to its source.</em></h1>
            <p className="mvp-lede">Turn a technical tender into a response sheet your team can review with the original wording, cited page, and highlight all in view.</p>
            <div className="mvp-hero-links"><a className="mvp-primary mvp-hero-primary" href="#upload">Review a tender <ArrowRight size={17} /></a><a className="mvp-secondary-link" href="#how-it-works">See the workflow <ArrowDownToLine size={15} /></a></div>
            <div className="mvp-hero-note"><ShieldCheck size={17} /><span><strong>Source first, human checked.</strong><small>Every extracted row starts in review.</small></span></div>
          </div>
          <div className="mvp-preview-card" id="evidence" aria-label="Illustrative source evidence preview">
            <div className="mvp-preview-head"><span className="mvp-preview-file"><FileText size={15} /> TENDER SPECIFICATION</span><span className="mvp-preview-sample">ILLUSTRATIVE PREVIEW</span></div>
            <div className="mvp-preview-page">
              <div className="mvp-preview-pagehead"><span>TECHNICAL SPECIFICATION</span><span>PAGE 08</span></div>
              <div className="mvp-preview-rule" />
              <div className="mvp-preview-line short" /><div className="mvp-preview-line" />
              <div className="mvp-preview-citation"><span className="mvp-preview-bbox" /><span>Minimum operating pressure shall be maintained across the full substrate area.</span></div>
              <div className="mvp-preview-line medium" /><div className="mvp-preview-line short" />
              <div className="mvp-preview-table"><span /><span /><span /><span /><span /><span /></div>
            </div>
            <div className="mvp-preview-foot"><span className="mvp-preview-foot-icon"><ScanSearch size={16} /></span><span><strong>Page-level evidence</strong><small>Quote and location stay together</small></span><span className="mvp-preview-page-tag">08 <ArrowUpRight size={12} /></span></div>
          </div>
        </section>
        <section className="mvp-proof-strip" aria-label="Review principles">
          <div><span className="mvp-proof-index">01</span><span><strong>Exact wording</strong><small>Quotes checked against page text</small></span></div>
          <div><span className="mvp-proof-index">02</span><span><strong>Visible evidence</strong><small>Open the page and see the highlight</small></span></div>
          <div><span className="mvp-proof-index">03</span><span><strong>Human review</strong><small>Nothing is marked checked for you</small></span></div>
        </section>
        <section className="mvp-start-section" id="upload">
          <div className="mvp-start-copy" id="how-it-works">
            <div className="mvp-eyebrow">A SHORT, TRACEABLE WORKFLOW</div>
            <h2>From tender PDF<br />to a reviewable sheet.</h2>
            <div className="mvp-step-list">
              <div><span>01</span><p><strong>Upload a text-based PDF</strong><small>Start with a tender up to 4 MB and 120 pages.</small></p></div>
              <div><span>02</span><p><strong>Check every source match</strong><small>Inspect the original page and its quote highlight.</small></p></div>
              <div><span>03</span><p><strong>Export the response sheet</strong><small>Share tender wording with blank OEM response fields.</small></p></div>
            </div>
          </div>
          <div className="mvp-upload-card">
            <div className="mvp-upload-card-heading"><span className="mvp-upload-step">START A REVIEW</span><span className="mvp-upload-private"><span /> This browser session</span></div>
            <form onSubmit={analyze}>
              <label className={`mvp-dropzone ${file ? "is-ready" : ""}`} htmlFor="tender-file">
                <input id="tender-file" type="file" accept="application/pdf,.pdf" onChange={selectFile} />
                <span className="mvp-upload-icon"><Upload size={20} /></span>
                {file ? <><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · ready to review</span></> : <><strong>Choose a tender PDF</strong><span>Browse your files to begin</span></>}
                <span className="mvp-browse-link">Browse files <ArrowUpRight size={14} /></span>
              </label>
              <button className="mvp-primary mvp-submit" type="submit" disabled={!file || busy}>
                {busy ? <><LoaderCircle className="mvp-spin" size={17} /> Reading and checking sources…</> : <>Extract requirements <ArrowRight size={17} /></>}
              </button>
              {error && <p className="mvp-error" role="alert">{error}</p>}
            </form>
            <div className="mvp-upload-limits"><span><FileCheck2 size={15} /> Text-based PDF only</span><span><ShieldCheck size={15} /> No file history saved</span></div>
          </div>
        </section>
        <footer className="mvp-landing-footer"><span>Tender Review <span>·</span> A focused single-user demo</span><span>Scanned PDFs need OCR and are not supported. Review the source before relying on any extracted requirement.</span></footer>
      </main>
    );
  }

  const checkedCount = analysis.requirements.filter((item) => item.reviewed).length;
  return (
    <main className="tender-mvp-root mvp-review-screen">
      <header className="mvp-topbar mvp-review-topbar">
        <a className="mvp-brand" href="/" aria-label="Start a new tender"><span className="mvp-brand-mark">T</span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Review workspace</small></span></a>
        <div className="mvp-topbar-right"><span className="mvp-file-name"><FileText size={15} />{analysis.filename}</span><span className="mvp-private"><span /> Single-user demo</span></div>
      </header>
      <section className="mvp-review-summarybar">
        <div className="mvp-review-title"><div className="mvp-eyebrow">TENDER REVIEW</div><h1>Technical requirements</h1><p>Review each extracted quote against its original page before you export.</p></div>
        <div className="mvp-review-stats" aria-label="Tender review summary">
          <div><span className="mvp-stat-icon"><FileCheck2 size={15} /></span><span><strong>{analysis.requirements.length}</strong><small>Source matched</small></span></div>
          <div><span className="mvp-stat-icon mvp-stat-icon-warn"><Check size={15} /></span><span><strong>{checkedCount}<i> / {analysis.requirements.length}</i></strong><small>Checked by you</small></span></div>
          <div><span className="mvp-stat-icon"><FileText size={15} /></span><span><strong>{analysis.pageCount}</strong><small>Tender pages</small></span></div>
        </div>
      </section>
      <div className="mvp-workspace">
        <section className="mvp-list-panel" aria-label="Extracted requirements">
          <div className="mvp-panel-heading"><div><span className="mvp-panel-kicker">REVIEW LIST</span><h2>Requirements <span>{analysis.requirements.length}</span></h2></div><button className="mvp-text-button" onClick={() => { setAnalysis(null); setFile(null); setError(null); }}><X size={15} /> New tender</button></div>
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
          <div className="mvp-evidence-heading"><div><span className="mvp-panel-kicker">SOURCE EVIDENCE</span><h2>{active && active.page === page ? `Page ${page} citation` : `Page ${page} source`}</h2></div><div className="mvp-evidence-actions"><button className="mvp-icon-button" onClick={() => setPage((current) => Math.max(1, current - 1))} aria-label="Previous page" disabled={page <= 1}><ArrowLeft size={16} /></button><span><strong>{String(page).padStart(2, "0")}</strong> / {analysis.pageCount}</span><button className="mvp-icon-button" onClick={() => setPage((current) => Math.min(analysis.pageCount, current + 1))} aria-label="Next page" disabled={page >= analysis.pageCount}><ArrowRight size={16} /></button></div></div>
          {file && <PdfEvidenceViewer file={file} pageNumber={page} selectedBox={active?.page === page ? active.bbox : null} />}
          <div className="mvp-citation-detail">
            <div className="mvp-citation-label"><span className="mvp-exact-dot" /> EXACT SOURCE QUOTE <span>·</span> PAGE {String(active?.page ?? page).padStart(2, "0")}</div>
            <blockquote>{active?.quote ?? "Choose a requirement to inspect its tender source."}</blockquote>
            <div className="mvp-review-actions"><span>{active?.reviewed ? "You checked this citation against the page." : page === active?.page && active?.bbox ? "Confirm the wording and highlight against the original." : "Open the cited page to check the quote and highlight."}</span><button disabled={!active || page !== active.page || !active.bbox} className={active?.reviewed ? "mvp-check-button is-checked" : "mvp-check-button"} onClick={markReviewed}>{active?.reviewed ? <><Check size={14} /> Checked</> : "Mark checked"}</button></div>
          </div>
        </section>
      </div>
    </main>
  );
}
