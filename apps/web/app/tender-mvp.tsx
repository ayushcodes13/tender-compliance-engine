"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { AlertTriangle, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, Check, FileCheck2, FileSpreadsheet, FileText, FolderOpen, LoaderCircle, Plus, Save, ScanSearch, ShieldCheck, Upload, X } from "lucide-react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { PdfEvidenceViewer } from "@/components/mvp/pdf-evidence-viewer";
import { PROCESSING_STEPS, formatElapsedSeconds, processingStepIndex, type ProcessingProgress } from "./processing-progress";
import { consumeAnalysisStream } from "./analysis-events";
import { visibleCitationEvidence, visibleCitationRequirement } from "./poc90-client-citation";
import { createOperatorAddedRequirement, insertRequirementByPhysicalPage, recoverDocumentIdentity } from "./operator-recovery";
import { prepareVisualComplianceRows } from "./visual-table";
import { complianceRowHeightTwips, reflowComplianceText, splitHeadingPrefix, verticalMergeAt } from "./compliance-format";
import { buildResponseSections } from "./response-sections";
import { buildResponseSheet, responseHeadingMergeKeys, removeResponseSheetRow, updateResponseSheetCell, splitRequirementSubpoints, addManualRequirementToSheet, promoteCandidateToSheet, reconcileScheduleDuplicates, detectScheduleDuplicates, type ResponseSheet } from "./response-sheet";
import type { RequirementSourceReference } from "./source-document";
import { describeRejectedSuggestion, type CoverageReport, type CoverageSourceRow, type RejectedSuggestion } from "./coverage-ledger";
import type { ClassificationReviewCandidate } from "./candidate-classification";
import {
  evaluateSheetCompliance,
  projectComplianceReportToSheet,
  type OEMComplianceAssessment,
  type ComplianceAssessmentReport,
  type ProductDocument,
  type ProductEvidenceCitation,
} from "./oem-compliance-engine";
import { parseProductPdfFile, getSampleProductDocument, getSampleProductFile } from "./product-document-parser";
import { resolveClientMaxFileBytes } from "./upload-limits";
import { decryptReviewSession, encryptReviewSession, verifyReviewSessionSource, type ReviewSession } from "./review-session";

gsap.registerPlugin(useGSAP, ScrollTrigger);

const CLIENT_MAX_FILE_BYTES = resolveClientMaxFileBytes();
const CLIENT_MAX_FILE_MEGABYTES = Math.round(CLIENT_MAX_FILE_BYTES / (1024 * 1024));

type BoundingBox = { x: number; y: number; width: number; height: number };
type Requirement = {
  id: string;
  text: string;
  parameter?: string;
  specifications?: string[];
  sourceCells?: string[];
  sourceColumnMap?: Array<{header: string; role: string}>;
  sourceSectionTitle?: string;
  sourceSectionHeadings?: string[];
  sourceSpecificationColumnIndex?: number;
  sourceSpecificationBlank?: boolean;
  remark?: string;
  rowType?: "section" | "requirement" | "optional_heading";
  headingPrefix?: string;
  nativeHeadingPrefix?: string;
  mergeWithNext?: boolean;
  continuationOfPrevious?: boolean;
  sourceRowHeight?: number;
  sourceTextHeight?: number;
  exportGroupId?: string;
  category: string;
  page: number;
  quote: string;
  sourceReference: RequirementSourceReference;
  selectableTextQuote?: string;
  unverifiedVisualCompletion?: string;
  bbox: BoundingBox | null;
  precision: "exact" | "visual-ocr" | "page-only" | "unverified";
  verdict?: "verbatim_pass" | "visual_pass" | "needs_human_review";
  needsHumanReview?: boolean;
  ocrWarning?: boolean;
  reviewed: boolean;
  isRevised?: boolean;
  revisedText?: string;
  originalSourceText?: string;
  isOperatorAdded?: boolean;
  isPromoted?: boolean;
};
type Analysis = {
  filename: string;
  pageCount: number;
  textPages: number;
  document: { documentId: string; documentVersionId: string; documentFingerprint: string; pageCount: number; inventoryIntegrity: "structurally-verified" | "unverified" };
  normalizedTables?: boolean;
  sectionTitle?: string;
  sectionHeading?: string;
  sourceColumns?: Array<{ header: string; role: "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other" }>;
  sheetTitle?: string;
  sheetHeading?: string;
  sheetProductTitle?: string;
  requirements: Requirement[];
  classificationReviewCandidates?: ClassificationReviewCandidate[];
  validationSummary?: {
    total: number;
    verbatimPass: number;
    visualPass: number;
    needsHumanReview: number;
  };
  rejectedCandidates: number;
  rejectedSuggestionDetails?: RejectedSuggestion[];
  coverage?: CoverageReport;
  extractionMode?: "rule-based-preview" | "structured-table" | "visual-compliance-sheet";
  reviewNote: string;
};

type FailureDiagnostics = {
  pageCount: number;
  candidateSuggestions: number;
  rejectedCandidates: number;
  rejectedSuggestionDetails: RejectedSuggestion[];
  rejectedSuggestionsNotShown: number;
  coverageSummary: CoverageReport["summary"];
  reviewPageNumbers: number[];
  reviewPagesNotShown: number;
  classificationReviewCandidates: ClassificationReviewCandidate[];
};

function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function coverageRowReviewLabel(row: CoverageSourceRow): string {
  if (row.disposition === "header") return `SOURCE HEADER ROW ${row.rowNumber} · REPEATED LABEL`;
  if (row.disposition === "empty") return `EMPTY SOURCE ROW ${row.rowNumber}`;
  if (row.sourceClassification === "ambiguous") return `AMBIGUOUS SOURCE ROW ${row.rowNumber} · NEEDS INSPECTION`;
  if (row.disposition === "unmapped") return `UNMAPPED SOURCE ROW ${row.rowNumber} · NEEDS INSPECTION`;
  if (row.semanticCoverageStatus === "possible_gap") return `SOURCE ROW ${row.rowNumber} · POSSIBLE OMISSION REPORTED`;
  if (row.semanticCoverageStatus === "ambiguous") return `SOURCE ROW ${row.rowNumber} · SEMANTIC AUDIT AMBIGUOUS`;
  if (row.semanticCoverageStatus === "audit_incomplete") return `SOURCE ROW ${row.rowNumber} · SEMANTIC AUDIT INCOMPLETE`;
  if (row.semanticCoverageStatus === "no_gap_reported") return `SOURCE ROW ${row.rowNumber} · NO GAP REPORTED · STILL UNVERIFIED`;
  if (row.sourceMatchedCandidates < row.candidateSuggestions) return `SOURCE ROW ${row.rowNumber} · COVERAGE MISMATCH`;
  return `SOURCE TABLE ROW ${row.rowNumber} · SOURCE MATCHED · COMPLETENESS UNVERIFIED`;
}

function coverageRowReviewMessage(row: CoverageSourceRow): string {
  if (row.disposition === "header") return `This detected row was classified as a repeated table header (${row.classificationReason.replaceAll("_", " ")}).`;
  if (row.disposition === "empty") return "This detected source row contains no selectable cell text.";
  if (row.sourceClassification === "ambiguous") return `The row classifier could not confidently determine the row's role (${row.classificationReason.replaceAll("_", " ")}). It was retained without creating a requirement; inspect the source page and decide its disposition.`;
  if (row.disposition === "unmapped") return `No extraction candidate was generated for this nonempty source row. Classification: ${row.sourceClassification.replaceAll("_", " ")} (${row.classificationReason.replaceAll("_", " ")}). Decide whether it is a requirement, heading, or other table content.`;
  if (row.semanticCoverageStatus === "possible_gap") return `A separate row audit reported a possible omission or partial representation. This is advisory; inspect the source row and candidate requirements. ${row.semanticCoverageNote ?? ""}`;
  if (row.semanticCoverageStatus === "ambiguous") return `A separate row audit could not determine whether every obligation is represented. Inspect the source row and candidate requirements. ${row.semanticCoverageNote ?? ""}`;
  if (row.semanticCoverageStatus === "audit_incomplete") return "The separate semantic row audit did not complete; source matching does not establish that every obligation is represented.";
  if (row.semanticCoverageStatus === "no_gap_reported") return `A separate row audit reported no possible gap, but this does not establish semantic completeness. Check every independent obligation in the row. ${row.semanticCoverageNote ?? ""}`;
  if (row.sourceMatchedCandidates < row.candidateSuggestions) {
    return `${row.sourceMatchedCandidates} of ${row.candidateSuggestions} generated candidates from this source row matched the source; inspect the unmatched candidate and confirm the row grouping.`;
  }
  return `${countLabel(row.candidateSuggestions, "candidate")} from this source row matched the source. Semantic completeness has not been assessed; check that every independent obligation in the full row is represented.`;
}


function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

function TenderReviewMark() {
  return (
    <svg className="mvp-brand-symbol" viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
      <path d="M8.5 4.5h10l6 6v16a1.5 1.5 0 0 1-1.5 1.5h-14A1.5 1.5 0 0 1 7.5 26V6a1.5 1.5 0 0 1 1-1.5Z" fill="#fff" />
      <path d="M18.5 4.5v6h6" stroke="#9BB8FF" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M11.5 14h8M11.5 18.5h4" stroke="#9AA8BD" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M10 22h11v3H10z" fill="#9BB8FF" />
      <path d="M10 21v-1.5h2M21 21v-1.5h-2M10 26v1.5h2M21 26v1.5h-2" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

export default function TenderMvpPage({ startAtUpload = false }: { startAtUpload?: boolean } = {}) {
  const motionRoot = useRef<HTMLElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [responseSheet, setResponseSheet] = useState<ResponseSheet | null>(null);
  const [sheetEdited, setSheetEdited] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [processing, setProcessing] = useState<ProcessingProgress | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [failureDiagnostics, setFailureDiagnostics] = useState<FailureDiagnostics | null>(null);
  const [exporting, setExporting] = useState(false);
  const [showSourceDetail, setShowSourceDetail] = useState(false);
  const sourceDrawerRef = useRef<HTMLDialogElement>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [coverageFocus, setCoverageFocus] = useState<{ page: number; row: CoverageSourceRow } | null>(null);
  const [addRequirementOpen, setAddRequirementOpen] = useState(false);
  const [newReqPage, setNewReqPage] = useState<number | string>(1);
  const [newReqHeading, setNewReqHeading] = useState("");
  const [newReqText, setNewReqText] = useState("");
  const [newReqCategory, setNewReqCategory] = useState("Technical");
  const [formError, setFormError] = useState<string | null>(null);
  const [productDoc, setProductDoc] = useState<ProductDocument | null>(null);
  const [productFile, setProductFile] = useState<File | null>(null);
  const [complianceReport, setComplianceReport] = useState<ComplianceAssessmentReport | null>(null);
  const [complianceProgressStage, setComplianceProgressStage] = useState<string | null>(null);
  const [activeDrawerDoc, setActiveDrawerDoc] = useState<"tender" | "product">("tender");
  const [productPage, setProductPage] = useState(1);
  const [productBox, setProductBox] = useState<BoundingBox | null>(null);
  const [productCitationEvidence, setProductCitationEvidence] = useState<ProductEvidenceCitation | null>(null);
  const [pendingResume, setPendingResume] = useState<ReviewSession | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [savePassphrase, setSavePassphrase] = useState("");
  const [confirmSavePassphrase, setConfirmSavePassphrase] = useState("");
  const [resumePassphrase, setResumePassphrase] = useState("");
  const [resumeSessionFile, setResumeSessionFile] = useState<File | null>(null);
  const sessionSaveDialogRef = useRef<HTMLDialogElement>(null);
  const sessionResumeDialogRef = useRef<HTMLDialogElement>(null);
  const sessionResumeInputRef = useRef<HTMLInputElement>(null);
  const sampleProductFileRef = useRef<File | null>(null);
  const manualIdCounterRef = useRef(0);
  const activeRequestRef = useRef<AbortController | null>(null);
  const processingStartedAtRef = useRef(0);

  useEffect(() => {
    if (!busy) return;
    const updateElapsed = () => setElapsedSeconds(Math.floor((Date.now() - processingStartedAtRef.current) / 1000));
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => () => activeRequestRef.current?.abort("upload screen closed"), []);

  useEffect(() => {
    const drawer = sourceDrawerRef.current;
    if (!drawer) return;
    if (sourceOpen && !drawer.open) drawer.showModal();
    if (!sourceOpen && drawer.open) drawer.close();
  }, [sourceOpen]);

  useGSAP(() => {
    const root = motionRoot.current;
    if (!root) return;

    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      if (root.classList.contains("mvp-landing")) {
        const entrance = gsap.timeline({ defaults: { ease: "power3.out" } });
        const topbar = root.querySelector(".mvp-landing-topbar");
        const brand = root.querySelector(".mvp-brand-mark");
        const headline = root.querySelector(".mvp-hero-copy h1");
        const supportingCopy = Array.from(root.querySelectorAll(".mvp-lede, .mvp-hero-links, .mvp-hero-note"));
        const productShot = root.querySelector(".mvp-product-shot");

        if (topbar && brand && headline && productShot) {
          entrance
            .fromTo(topbar, { autoAlpha: 0, y: -8 }, { autoAlpha: 1, y: 0, duration: 0.38 })
            .fromTo(brand, { scale: 0.94, rotation: -4 }, { scale: 1, rotation: 0, duration: 0.36 }, "<+0.04")
            .fromTo(headline, { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: 0.48 }, "<+0.08")
            .fromTo(supportingCopy, { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.38, stagger: 0.07 }, "<+0.04")
            .fromTo(productShot, { autoAlpha: 0, y: 16, scale: 0.985 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.56 }, "<+0.08");
        }

        root.querySelectorAll<HTMLElement>(".mvp-motion-section:not(.mvp-landing-hero)").forEach((section) => {
          gsap.fromTo(section, { autoAlpha: 0, y: 16 }, {
            autoAlpha: 1,
            y: 0,
            duration: 0.48,
            ease: "power3.out",
            scrollTrigger: { trigger: section, scroller: root, start: "top 88%", once: true },
          });
        });
      } else if (root.classList.contains("mvp-upload-screen")) {
        gsap.fromTo(".mvp-upload-intro, .mvp-upload-card", { autoAlpha: 0, y: 12 }, {
          autoAlpha: 1,
          y: 0,
          duration: 0.42,
          ease: "power3.out",
          stagger: 0.09,
        });
      } else if (root.classList.contains("mvp-review-screen")) {
        gsap.fromTo(".mvp-review-topbar, .mvp-review-summarybar, .mvp-sheet-panel", { autoAlpha: 0, y: 10 }, {
          autoAlpha: 1,
          y: 0,
          duration: 0.36,
          ease: "power3.out",
          stagger: 0.07,
        });
      }
    });

    return () => media.revert();
  }, { scope: motionRoot, dependencies: [analysis?.filename, startAtUpload], revertOnUpdate: true });

  const active = useMemo(
    () => analysis?.requirements.find((item) => item.id === activeId) ?? analysis?.requirements[0] ?? null,
    [analysis, activeId],
  );
  const sourcePageRequirement = visibleCitationRequirement(active, page, coverageFocus?.page);
  const displayedCitationEvidence = visibleCitationEvidence(active, page, coverageFocus?.page);

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    setPendingResume(null);
    const previousRequest = activeRequestRef.current;
    activeRequestRef.current = null;
    previousRequest?.abort("a different tender was selected");
    setBusy(false);
    setError(null);
    setFailureDiagnostics(null);
    setProcessing(null);
    setAnalysis(null);
    setResponseSheet(null);
    setSheetEdited(false);
    setActiveId(null);
    setCoverageFocus(null);
    setElapsedSeconds(0);
    const selected = event.target.files?.[0] ?? null;
    if (selected && selected.size > CLIENT_MAX_FILE_BYTES) {
      setError(`The selected file (${(selected.size / 1024 / 1024).toFixed(1)} MB) exceeds the ${CLIENT_MAX_FILE_MEGABYTES} MB limit for this deployment. Choose a smaller PDF.`);
      setFile(null);
      return;
    }
    setFile(selected);
  }

  async function resumeSourceFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    if (!selected || !pendingResume) return;
    event.target.value = "";
    if (selected.size > 32 * 1024 * 1024 || !selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Choose the original PDF used for this review session.");
      return;
    }
    try {
      setSessionBusy(true);
      if (!await verifyReviewSessionSource(selected, pendingResume.documentFingerprint)) {
        setError("This PDF does not match the saved session. Choose the exact original file; citations were not restored.");
        return;
      }
      setFile(selected);
      const restoredRequirements = pendingResume.analysis.requirements as unknown as Requirement[];
      setAnalysis(pendingResume.analysis as unknown as Analysis);
      setResponseSheet(pendingResume.responseSheet as ResponseSheet);
      setSheetEdited(pendingResume.sheetEdited);
      setActiveId(restoredRequirements[0]?.id ?? null);
      setPage(restoredRequirements[0]?.page ?? 1);
      setPendingResume(null);
      setError(null);
      setProcessing({ stage: "complete", message: "Saved review restored. Source PDF fingerprint verified." });
    } catch {
      setError("The selected PDF could not be verified. Choose the original file and try again.");
    } finally {
      setSessionBusy(false);
    }
  }

  async function saveReviewSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!analysis || !responseSheet) return;
    if (savePassphrase !== confirmSavePassphrase) {
      setSessionError("The passphrases do not match.");
      return;
    }
    try {
      setSessionBusy(true);
      setSessionError(null);
      const blob = await encryptReviewSession({ analysis, responseSheet, sheetEdited }, savePassphrase, {
        documentFingerprint: analysis.document.documentFingerprint,
        filename: analysis.filename,
      });
      downloadBlob(blob, `${analysis.filename.replace(/\.pdf$/i, "")}-review.tce-review`);
      sessionSaveDialogRef.current?.close();
      setSavePassphrase("");
      setConfirmSavePassphrase("");
    } catch (cause) {
      setSessionError(cause instanceof Error ? cause.message : "The review session could not be saved.");
    } finally {
      setSessionBusy(false);
    }
  }

  async function restoreReviewSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resumeSessionFile) {
      setSessionError("Choose a Tender Review session file first.");
      return;
    }
    try {
      setSessionBusy(true);
      setSessionError(null);
      const restored = await decryptReviewSession(resumeSessionFile, resumePassphrase);
      setPendingResume(restored);
      setFile(null);
      setAnalysis(null);
      setResponseSheet(null);
      setSheetEdited(false);
      setError(null);
      setProcessing(null);
      sessionResumeDialogRef.current?.close();
      setResumePassphrase("");
      setResumeSessionFile(null);
    } catch (cause) {
      setSessionError(cause instanceof Error ? cause.message : "The review session could not be restored.");
    } finally {
      setSessionBusy(false);
    }
  }

  function openSaveSessionDialog() {
    setSessionError(null);
    sessionSaveDialogRef.current?.showModal();
  }

  function openResumeSessionDialog() {
    setSessionError(null);
    sessionResumeDialogRef.current?.showModal();
  }

  const reviewSessionDialogs = <>
    <dialog ref={sessionSaveDialogRef} className="mvp-modal-dialog" aria-label="Save encrypted review session" onClose={() => { setSavePassphrase(""); setConfirmSavePassphrase(""); setSessionError(null); }}>
      <div className="mvp-modal-backdrop" onClick={() => sessionSaveDialogRef.current?.close()} />
      <div className="mvp-modal-content">
        <div className="mvp-modal-header"><div><span className="mvp-panel-kicker">PRIVATE SESSION FILE</span><h2>Save this review</h2></div><button type="button" className="mvp-icon-button" aria-label="Close save session dialog" onClick={() => sessionSaveDialogRef.current?.close()}><X size={18} /></button></div>
        <p className="mvp-modal-desc">The review data is encrypted in your browser and downloaded to your device. Choose a long, unique passphrase. The PDF is not included; keep the original PDF and passphrase because both are required to resume with working citations.</p>
        <form className="mvp-modal-form" onSubmit={saveReviewSession}>
          <label>Passphrase<input type="password" autoComplete="new-password" minLength={12} maxLength={512} value={savePassphrase} onChange={(event) => setSavePassphrase(event.target.value)} required /></label>
          <label>Confirm passphrase<input type="password" autoComplete="new-password" minLength={12} maxLength={512} value={confirmSavePassphrase} onChange={(event) => setConfirmSavePassphrase(event.target.value)} required /></label>
          {sessionError && <p className="mvp-error" role="alert">{sessionError}</p>}
          <div className="mvp-modal-actions"><button type="button" className="mvp-text-button" onClick={() => sessionSaveDialogRef.current?.close()}>Cancel</button><button type="submit" className="mvp-primary" disabled={sessionBusy}>{sessionBusy ? <><LoaderCircle className="mvp-spin" size={16} /> Encrypting…</> : <><Save size={16} /> Download encrypted file</>}</button></div>
        </form>
      </div>
    </dialog>
    <dialog ref={sessionResumeDialogRef} className="mvp-modal-dialog" aria-label="Resume encrypted review session" onClose={() => { setResumePassphrase(""); setResumeSessionFile(null); setSessionError(null); if (sessionResumeInputRef.current) sessionResumeInputRef.current.value = ""; }}>
      <div className="mvp-modal-backdrop" onClick={() => sessionResumeDialogRef.current?.close()} />
      <div className="mvp-modal-content">
        <div className="mvp-modal-header"><div><span className="mvp-panel-kicker">PRIVATE SESSION FILE</span><h2>Resume a saved review</h2></div><button type="button" className="mvp-icon-button" aria-label="Close resume session dialog" onClick={() => sessionResumeDialogRef.current?.close()}><X size={18} /></button></div>
        <p className="mvp-modal-desc">Choose your encrypted .tce-review file and enter its passphrase. Next, select the original PDF; its SHA-256 fingerprint must match before citations and review edits are restored.</p>
        <form className="mvp-modal-form" onSubmit={restoreReviewSession}>
          <label>Encrypted review file<input ref={sessionResumeInputRef} type="file" accept=".tce-review,application/vnd.tender-review-session+json" onChange={(event) => setResumeSessionFile(event.target.files?.[0] ?? null)} required /></label>
          <label>Passphrase<input type="password" autoComplete="current-password" minLength={12} maxLength={512} value={resumePassphrase} onChange={(event) => setResumePassphrase(event.target.value)} required /></label>
          {sessionError && <p className="mvp-error" role="alert">{sessionError}</p>}
          <div className="mvp-modal-actions"><button type="button" className="mvp-text-button" onClick={() => sessionResumeDialogRef.current?.close()}>Cancel</button><button type="submit" className="mvp-primary" disabled={sessionBusy}>{sessionBusy ? <><LoaderCircle className="mvp-spin" size={16} /> Unlocking…</> : <><FolderOpen size={16} /> Continue</>}</button></div>
        </form>
      </div>
    </dialog>
  </>;

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    const requestController = new AbortController();
    activeRequestRef.current = requestController;
    processingStartedAtRef.current = Date.now();
    setElapsedSeconds(0);
    setBusy(true);
    setError(null);
    setFailureDiagnostics(null);
    setProcessing({ stage: "uploading", message: "Uploading and validating your PDF" });
    const body = new FormData();
    body.set("file", file);
    let keepTerminalState = false;
    try {
      const response = await fetch("/api/analyze", { method: "POST", body, signal: requestController.signal });
      const result = await consumeAnalysisStream<{ ok: boolean; analysis?: Analysis; error?: string; pageCount?: number; candidateSuggestions?: number; rejectedCandidates?: number; rejectedSuggestionDetails?: RejectedSuggestion[]; rejectedSuggestionsNotShown?: number; classificationReviewCandidates?: ClassificationReviewCandidate[]; coverageSummary?: CoverageReport["summary"]; reviewPageNumbers?: number[]; reviewPagesNotShown?: number }>(response, {
        signal: requestController.signal,
        onProgress: (progress) => {
          if (activeRequestRef.current === requestController) setProcessing(progress);
        },
      });
      if (activeRequestRef.current !== requestController) return;
      if (!result.ok) {
        if (result.coverageSummary && result.rejectedSuggestionDetails) {
          setFailureDiagnostics({
            pageCount: result.pageCount ?? result.coverageSummary.documentPages,
            candidateSuggestions: result.candidateSuggestions ?? 0,
            rejectedCandidates: result.rejectedCandidates ?? result.rejectedSuggestionDetails.length,
            rejectedSuggestionDetails: result.rejectedSuggestionDetails,
            rejectedSuggestionsNotShown: result.rejectedSuggestionsNotShown ?? 0,
            coverageSummary: result.coverageSummary,
            reviewPageNumbers: result.reviewPageNumbers ?? [],
            reviewPagesNotShown: result.reviewPagesNotShown ?? 0,
            classificationReviewCandidates: result.classificationReviewCandidates ?? [],
          });
        }
        throw new Error(result.error || "The tender could not be processed.");
      }
      const payload = result.analysis as Analysis;
      setProcessing({ stage: "preparing", message: "Preparing the editable response sheet" });
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      requestController.signal.throwIfAborted();
      const preparedSheet = buildResponseSheet(payload);
      setAnalysis(payload);
      setResponseSheet(preparedSheet);
      setSheetEdited(false);
      setActiveId(payload.requirements[0]?.id ?? null);
      setPage(payload.requirements[0]?.page ?? 1);
      const elapsed = Math.floor((Date.now() - processingStartedAtRef.current) / 1000);
      setElapsedSeconds(elapsed);
      setProcessing({ stage: "complete", message: `Ready for review after ${formatElapsedSeconds(elapsed)}.` });
      keepTerminalState = true;
    } catch (cause) {
      if (activeRequestRef.current !== requestController) return;
      keepTerminalState = true;
      const elapsed = Math.floor((Date.now() - processingStartedAtRef.current) / 1000);
      setElapsedSeconds(elapsed);
      if (requestController.signal.aborted) {
        setError(null);
        setProcessing({ stage: "cancelled", message: `Processing cancelled after ${formatElapsedSeconds(elapsed)}. The selected PDF is ready to try again.` });
      } else {
        setError(cause instanceof Error ? cause.message : "The tender could not be processed.");
        setProcessing({ stage: "error", message: `Processing stopped after ${formatElapsedSeconds(elapsed)}.` });
      }
    } finally {
      if (activeRequestRef.current === requestController) {
        activeRequestRef.current = null;
        setBusy(false);
        if (!keepTerminalState) setProcessing(null);
      }
    }
  }

  function cancelAnalysis() {
    activeRequestRef.current?.abort("user cancelled processing");
  }

  function openRequirement(item: Requirement) {
    setActiveDrawerDoc("tender");
    setCoverageFocus(null);
    setActiveId(item.id);
    setPage(item.page);
    setSourceOpen(true);
  }

  function openProductCitation(citation: ProductEvidenceCitation) {
    setActiveDrawerDoc("product");
    setProductPage(citation.page);
    setProductBox(citation.bbox);
    setProductCitationEvidence(citation);
    setSourceOpen(true);
  }

  function handleProductFileUpload(e: ChangeEvent<HTMLInputElement>) {
    const uploaded = e.target.files?.[0];
    if (uploaded) {
      setProductFile(uploaded);
      void parseProductPdfFile(uploaded).then((parsed) => {
        setProductDoc(parsed);
      });
    }
  }

  function handleLoadSampleProduct() {
    const sample = getSampleProductDocument();
    setProductDoc(sample);
    if (!sampleProductFileRef.current) {
      sampleProductFileRef.current = getSampleProductFile();
    }
    setProductFile(sampleProductFileRef.current);
  }

  async function handleRunCompliance() {
    if (!responseSheet || !analysis) return;

    let doc = productDoc;
    if (!doc) {
      if (productFile) {
        setComplianceProgressStage("Parsing uploaded OEM product documentation…");
        doc = await parseProductPdfFile(productFile);
        setProductDoc(doc);
      } else {
        setComplianceProgressStage("Loading verified OEM product technical specifications…");
        doc = getSampleProductDocument();
        setProductDoc(doc);
        if (!sampleProductFileRef.current) {
          sampleProductFileRef.current = getSampleProductFile();
        }
        setProductFile(sampleProductFileRef.current);
      }
    }

    setComplianceProgressStage("Extracting numerical constraints, tolerances, and technical parameters…");
    await new Promise((resolve) => setTimeout(resolve, 350));

    setComplianceProgressStage("Evaluating compliance against tender requirements & verifying citations…");
    await new Promise((resolve) => setTimeout(resolve, 450));

    const tenderReqs = analysis.requirements.map((r) => ({
      id: r.id,
      page: r.page,
      quote: r.quote,
      bbox: r.bbox,
    }));

    const report = evaluateSheetCompliance(responseSheet, tenderReqs, doc, analysis.filename);
    setComplianceReport(report);

    setComplianceProgressStage("Synthesizing two-sided compliance matrix with clickable source citations…");
    await new Promise((resolve) => setTimeout(resolve, 300));

    const enrichedSheet = projectComplianceReportToSheet(responseSheet, report);
    setResponseSheet(enrichedSheet);
    setSheetEdited(true);

    setComplianceProgressStage(null);
  }

  function markReviewed() {
    if (!analysis || !active) return;
    setAnalysis({
      ...analysis,
      requirements: analysis.requirements.map((item) => item.id === active.id ? { ...item, reviewed: !item.reviewed } : item),
    });
  }

  function updateSheetCell(rowId: string, columnIndex: number, value: string) {
    if (!responseSheet) return;
    const column = responseSheet.columns[columnIndex];
    const targetRow = responseSheet.rows.find((r) => r.id === rowId);
    setResponseSheet(updateResponseSheetCell(responseSheet, rowId, columnIndex, value));
    setSheetEdited(true);

    // If a requirement, heading, or source wording was edited, invalidate its verified review state
    // and keep immutable original source wording
    if ((column?.role === "requirement" || column?.role === "heading" || column?.role === "source") && targetRow && targetRow.values[columnIndex] !== value) {
      if (analysis) {
        const linkedIds = new Set([targetRow.sourceRequirementId, ...(targetRow.sourceRequirementIds || [])].filter(Boolean));
        if (linkedIds.size > 0) {
          setAnalysis({
            ...analysis,
            requirements: analysis.requirements.map((item) => {
              if (linkedIds.has(item.id)) {
                return {
                  ...item,
                  reviewed: false,
                  isRevised: true,
                  revisedText: column.role === "requirement" ? value : item.revisedText,
                  originalSourceText: item.originalSourceText || item.text,
                };
              }
              return item;
            }),
          });
        }
      }
    }
  }

  function removeSheetRow(rowId: string) {
    if (!responseSheet) return;
    const targetRow = responseSheet.rows.find((r) => r.id === rowId);
    setResponseSheet(removeResponseSheetRow(responseSheet, rowId));
    setSheetEdited(true);
    if (analysis && targetRow) {
      const targetId = targetRow.sourceRequirementId;
      const item = analysis.requirements.find((r) => r.id === targetId);
      if (item?.isOperatorAdded) {
        setAnalysis({
          ...analysis,
          requirements: analysis.requirements.filter((r) => r.id !== targetId),
        });
      }
    }
  }

  function handleAddRequirement(e: FormEvent) {
    e.preventDefault();
    if (!analysis || !responseSheet) return;
    const pageNum = Number(newReqPage);
    if (!Number.isInteger(pageNum) || pageNum < 1 || pageNum > analysis.pageCount) {
      setFormError(`Please enter a valid page number between 1 and ${analysis.pageCount}.`);
      return;
    }
    if (!newReqText.trim()) {
      setFormError("Requirement wording is required.");
      return;
    }

    const reqId = `req-manual-${Date.now()}-${++manualIdCounterRef.current}`;
    const newReq: Requirement = createOperatorAddedRequirement({
      id: reqId,
      page: pageNum,
      text: newReqText,
      category: newReqCategory,
      heading: newReqHeading,
      document: analysis.document,
    });

    const updatedAnalysisRequirements = insertRequirementByPhysicalPage(analysis.requirements, newReq);
    const updatedSheet = addManualRequirementToSheet(responseSheet, {
      id: reqId,
      page: pageNum,
      text: newReqText.trim(),
      heading: newReqHeading.trim() || undefined,
      category: newReqCategory.trim() || "Technical",
    });

    setAnalysis({
      ...analysis,
      requirements: updatedAnalysisRequirements,
    });
    setResponseSheet(updatedSheet);
    setSheetEdited(true);
    setAddRequirementOpen(false);
    setNewReqText("");
    setNewReqHeading("");
    setNewReqCategory("Technical");
    setFormError(null);
    setActiveId(reqId);
    setPage(pageNum);
  }

  function handlePromoteCandidate(candidate: ClassificationReviewCandidate, candidateIndex: number) {
    if (!analysis || !responseSheet) return;
    const { sheet: updatedSheet, requirementId } = promoteCandidateToSheet(responseSheet, candidate);
    const promotedReq: Requirement = {
      id: requirementId,
      text: candidate.quote,
      quote: candidate.quote,
      page: candidate.page,
      category: "Promoted Specification",
      rowType: "requirement",
      // A parser bbox is in PDF viewport units, not the percentages required
      // for the UI overlay. Preserve its reference, but inspect the page.
      precision: "page-only",
      verdict: "needs_human_review",
      needsHumanReview: true,
      reviewed: false,
      isPromoted: true,
      bbox: null,
      sourceReference: candidate.sourceReference,
    };

    const updatedRequirements = insertRequirementByPhysicalPage(analysis.requirements, promotedReq);
    const remainingCandidates = (analysis.classificationReviewCandidates ?? []).filter((_, i) => i !== candidateIndex);

    setAnalysis({
      ...analysis,
      requirements: updatedRequirements,
      classificationReviewCandidates: remainingCandidates,
    });
    setResponseSheet(updatedSheet);
    setSheetEdited(true);
    setActiveId(requirementId);
    setPage(candidate.page);
  }

  function handlePromoteFromDiagnostics(candidate: ClassificationReviewCandidate, candidateIndex: number) {
    if (!failureDiagnostics) return;
    const recoveredDocument = recoverDocumentIdentity(candidate.sourceReference, failureDiagnostics.pageCount);
    if (!recoveredDocument || candidate.sourceReference.physicalPdfPageNumber !== candidate.page) {
      setError("The original document reference could not be verified. Keep this candidate in review and inspect the PDF.");
      return;
    }
    const promotedReqId = candidate.candidateId || `req-promoted-${Date.now()}-${candidateIndex}`;
    const promotedReq: Requirement = {
      id: promotedReqId,
      text: candidate.quote,
      quote: candidate.quote,
      page: candidate.page,
      category: "Promoted Specification",
      rowType: "requirement",
      // A parser bbox is in PDF viewport units, not the percentages required
      // for the UI overlay. Preserve its reference, but inspect the page.
      precision: "page-only",
      verdict: "needs_human_review",
      needsHumanReview: true,
      reviewed: false,
      isPromoted: true,
      bbox: null,
      sourceReference: candidate.sourceReference,
    };

    const remaining = failureDiagnostics.classificationReviewCandidates.filter((_, i) => i !== candidateIndex);
    const newAnalysis: Analysis = {
      filename: file?.name || "Tender Document",
      pageCount: failureDiagnostics.pageCount,
      textPages: failureDiagnostics.coverageSummary.documentPages,
      document: recoveredDocument,
      requirements: [promotedReq],
      classificationReviewCandidates: remaining,
      rejectedCandidates: failureDiagnostics.rejectedCandidates,
      rejectedSuggestionDetails: failureDiagnostics.rejectedSuggestionDetails,
      coverage: {
        summary: failureDiagnostics.coverageSummary,
        pages: [],
      },
      reviewNote: "Operator-recovered from a partial analysis. Original source identity is retained, but document inventory integrity and extraction completeness have not been verified. Inspect the tender before using this sheet.",
    };

    const sheet = buildResponseSheet(newAnalysis);
    setAnalysis(newAnalysis);
    setResponseSheet(sheet);
    setSheetEdited(true);
    setFailureDiagnostics(null);
    setActiveId(promotedReqId);
    setPage(candidate.page);
  }

  function resetResponseSheet() {
    if (!analysis) return;
    setAnalysis({
      ...analysis,
      requirements: analysis.requirements.map((item) => ({
        ...item,
        isRevised: false,
        revisedText: undefined,
      })),
    });
    setResponseSheet(buildResponseSheet(analysis));
    setSheetEdited(false);
  }

  function handleReconcileDuplicates() {
    if (!responseSheet) return;
    const reconciled = reconcileScheduleDuplicates(responseSheet);
    setResponseSheet(reconciled);
    setSheetEdited(true);
  }

  async function exportDocx() {
    if (!analysis || !responseSheet?.rows.length) return;
    setExporting(true);
    setError(null);
    try {
      if (responseSheet.layout === "sectioned" || responseSheet.rows.some(row => row.section)) {
        const { createSectionedDocxBlob } = await import("./sectioned-exports");
        downloadBlob(await createSectionedDocxBlob(responseSheet), `${analysis.filename.replace(/\.pdf$/i, "")}-technical-response.docx`);
        return;
      }

      const { AlignmentType, BorderStyle, Document, HeadingLevel, HeightRule, Packer, Paragraph, Table, TableCell, TableLayoutType, TableRow, TextRun, VerticalAlignTable, VerticalMergeType, WidthType } = await import("docx");
      const cell = (text: string, bold = false, alignment?: (typeof AlignmentType)[keyof typeof AlignmentType], size = 19, indent = 0, headingPrefix?: string, verticalMerge?: "restart" | "continue") => {
        const displayText = verticalMerge === "continue" ? "" : text;
        const headingParts = splitHeadingPrefix(displayText, headingPrefix);
        return new TableCell({
        children: [new Paragraph({
          alignment,
          ...(indent ? { indent: { left: indent } } : {}),
          children: headingParts
            ? [new TextRun({ text: headingParts.heading, bold: true, size, font: "Calibri" }), new TextRun({ text: headingParts.remainder, bold, size, font: "Calibri" })]
            : [new TextRun({ text: displayText, bold, size, font: "Calibri" })],
        })],
        margins: { top: 100, bottom: 100, left: 120, right: 120 },
        ...(verticalMerge ? { verticalMerge: verticalMerge === "restart" ? VerticalMergeType.RESTART : VerticalMergeType.CONTINUE } : {}),
        });
      };
      const structured = analysis.extractionMode === "structured-table";
      const complianceSheet = false;
      const complianceCell = (text: string, bold = false, size = 19, alignment?: (typeof AlignmentType)[keyof typeof AlignmentType], rowType?: Requirement["rowType"], headingPrefix?: string, verticalAlign?: (typeof VerticalAlignTable)[keyof typeof VerticalAlignTable], pageContinuation?: string) => {
        const segments = pageContinuation === undefined ? [text] : [pageContinuation, text];
        return new TableCell({
          ...(verticalAlign ? { verticalAlign } : {}),
          children: segments.map((segment, segmentIndex) => {
            const isContinuation = segmentIndex === 0 && segments.length > 1;
            const segmentRowType = isContinuation ? undefined : rowType;
            const segmentHeadingPrefix = isContinuation ? undefined : headingPrefix;
            const letterRow = /^[a-z]\)/i.test(segment);
            return new Paragraph({
              style: "TableParagraph",
              alignment: letterRow && !segment.includes("\n") ? AlignmentType.JUSTIFIED : alignment,
              ...(segmentRowType === "section" ? { indent: { left: 102 } } : letterRow ? { indent: { left: 801, hanging: 348 } } : {}),
              ...(isContinuation ? { border: { bottom: { style: BorderStyle.SINGLE, size: 4, space: 0, color: "000000" } } } : {}),
              children: segment.split("\n").flatMap((line, index) => {
                const headingParts = index === 0 ? splitHeadingPrefix(line, segmentHeadingPrefix) : null;
                return [
                  ...(index > 0 ? [new TextRun({ break: 1 })] : []),
                  ...(headingParts
                    ? [new TextRun({ text: headingParts.heading, bold: true, size }), new TextRun({ text: headingParts.remainder, bold, size })]
                    : [new TextRun({ text: line, bold, size })]),
                ];
              }),
            });
          }),
          margins: { left: 0, right: 0 },
          borders: { bottom: { style: BorderStyle.SINGLE, size: 4, space: 0, color: "000000" } },
        });
      };
      const complianceTable = (tableRows: Array<InstanceType<typeof TableRow>>) => new Table({
        rows: tableRows,
        width: { size: 11_199, type: WidthType.DXA },
        columnWidths: [8_162, 1_620, 1_417],
        layout: TableLayoutType.FIXED,
        indent: { size: -418, type: WidthType.DXA },
        margins: { left: 0, right: 0 },
        borders: {
          top: { style: BorderStyle.SINGLE, size: 6, space: 0, color: "000000" },
          left: { style: BorderStyle.SINGLE, size: 6, space: 0, color: "000000" },
          bottom: { style: BorderStyle.SINGLE, size: 6, space: 0, color: "000000" },
          right: { style: BorderStyle.SINGLE, size: 6, space: 0, color: "000000" },
          insideHorizontal: { style: BorderStyle.SINGLE, size: 6, space: 0, color: "000000" },
          insideVertical: { style: BorderStyle.SINGLE, size: 6, space: 0, color: "000000" },
        },
      });
      const complianceHeader = new TableRow({ height: { value: 670, rule: HeightRule.ATLEAST }, children: [
        complianceCell("Technical Parameters NIQ", true, 19, AlignmentType.CENTER, undefined, undefined, VerticalAlignTable.BOTTOM),
        complianceCell("Remark", true, 19, AlignmentType.CENTER, undefined, undefined, VerticalAlignTable.BOTTOM),
        complianceCell("Compliance\nY/N", true, 19, AlignmentType.CENTER, undefined, undefined, VerticalAlignTable.TOP),
      ] });
      const complianceSpacer = new TableRow({ height: { value: 226, rule: HeightRule.ATLEAST }, children: [complianceCell("", false, 16), complianceCell("", false, 16), complianceCell("", false, 16)] });
      const complianceRow = (item: Requirement, preserveLineItems = false, pageContinuation?: string) => new TableRow({
        height: { value: complianceRowHeightTwips(item.sourceRowHeight, item.rowType === "section" || item.rowType === "optional_heading"), rule: HeightRule.ATLEAST },
        children: [
          complianceCell(reflowComplianceText(item.text, preserveLineItems), item.rowType === "section" && !item.headingPrefix, 19, undefined, item.rowType, item.headingPrefix, undefined, pageContinuation === undefined ? undefined : reflowComplianceText(pageContinuation, preserveLineItems)),
          complianceCell(reflowComplianceText(item.remark ?? ""), false, 16, AlignmentType.CENTER, undefined, undefined, undefined, pageContinuation === undefined ? undefined : ""),
          complianceCell("", false, 16, undefined, undefined, undefined, undefined, pageContinuation === undefined ? undefined : ""),
        ],
      });
      const optionalHeadingIndex = analysis.requirements.findIndex((item) => item.rowType === "optional_heading");
      const mainComplianceItems = (optionalHeadingIndex < 0 ? analysis.requirements : analysis.requirements.slice(0, optionalHeadingIndex))
        .filter((item) => item.rowType !== "optional_heading")
      const mainComplianceExportRows = prepareVisualComplianceRows(mainComplianceItems);
      const optionalComplianceRows = (optionalHeadingIndex < 0 ? [] : analysis.requirements.slice(optionalHeadingIndex + 1))
        .map((item) => complianceRow(item, true));
      const mainComplianceTableRows = [
        complianceHeader,
        complianceSpacer,
        ...mainComplianceExportRows.map((item) => complianceRow(item)),
      ];
      const sourceColumns = structured
        ? [
          { header: "Parameter", role: "heading" as const },
          { header: "Required Specification", role: "specification" as const },
          { header: "Compliance (Yes / No)", role: "compliance" as const },
          { header: "Any remarks", role: "remark" as const },
        ]
        : analysis.sourceColumns?.length
          ? analysis.sourceColumns
          : [{ header: "Tender specification", role: "specification" as const }];
      const exportColumns = responseSheet.columns;
      const responseRows = responseSheet.rows;
      const headingColumnIndices = exportColumns
        .map((column, index) => (column.role === "heading" ? index : -1))
        .filter((index) => index >= 0);
      const rows = [
        new TableRow({ tableHeader: true, children: exportColumns.map((column) => cell(column.header, true, AlignmentType.CENTER)) }),
        ...responseRows.map((item, rowIndex) => new TableRow({
          cantSplit: true,
          children: item.values.map((value, columnIndex) => {
            const isHeading = headingColumnIndices.includes(columnIndex);
            const colValues = responseRows.map((r) => r.values[columnIndex]);
            const merge = isHeading
              ? verticalMergeAt(colValues, rowIndex)
              : undefined;
            return cell(value, item.section, undefined, 19, 0, undefined, merge);
          }),
        })),
      ];
      const complianceContent = [
        new Paragraph({
          children: [new TextRun({ text: analysis.sheetTitle || "COMPLIANCE SHEET", bold: true, underline: {}, size: 23 })],
          alignment: AlignmentType.CENTER,
          indent: { right: 55 },
          spacing: { before: 180, after: 630 },
        }),
        ...(analysis.sheetHeading ? [new Paragraph({
          children: [
            new TextRun({ text: analysis.sheetHeading, bold: true, size: 21 }),
            ...(analysis.sheetProductTitle ? [new TextRun({ text: ` ${analysis.sheetProductTitle}`, bold: true, underline: {}, color: "7F7F7F", size: 24 })] : []),
          ],
          style: "BodyText",
        })] : []),
        ...(mainComplianceTableRows.length ? [complianceTable(mainComplianceTableRows)] : []),
        ...(optionalHeadingIndex >= 0 ? [
          new Paragraph(""),
          new Paragraph(""),
          new Paragraph(""),
          new Paragraph({
            children: [new TextRun({ text: `${analysis.requirements[optionalHeadingIndex].text.replace(/:+$/, "")}:`, bold: true, underline: {}, size: 21 })],
            style: "BodyText",
            indent: { left: 1_200 },
            spacing: { before: 120 },
          }),
          new Paragraph(""),
          complianceTable(optionalComplianceRows),
        ] : []),
      ];
      const commonContent = complianceSheet ? complianceContent : [
        new Paragraph({
          children: [new TextRun({ text: structured ? analysis.sectionTitle ?? "Section 4 – Technical specifications" : "Tender Technical Requirements", bold: structured, size: structured ? 24 : 56, font: structured ? "Calibri" : undefined })],
          heading: structured ? undefined : HeadingLevel.TITLE,
          alignment: structured ? AlignmentType.CENTER : undefined,
          spacing: { after: 80 },
        }),
        ...(structured && analysis.sectionHeading ? [new Paragraph({
          children: [new TextRun({ text: analysis.sectionHeading, bold: true, size: 22, font: "Calibri" })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 180 },
        })] : []),
        ...(structured ? [new Paragraph({
          children: [new TextRun({ text: `Source tender: ${analysis.filename} · page ${[...new Set(analysis.requirements.map((item) => item.page))].join(", ")}`, size: 18, font: "Calibri" })],
          spacing: { after: 100 },
        })] : [
          new Paragraph({ text: `Source tender: ${analysis.filename}` }),
          new Paragraph({ text: `${responseRows.length} worksheet rows · ${analysis.requirements.filter((item) => item.reviewed).length} source items checked by reviewer` }),
          new Paragraph({ text: analysis.extractionMode === "rule-based-preview" ? "Rule-based preview for human review. Candidate extraction may miss requirements and does not guarantee tender completeness." : "AI-assisted draft for human review. This document does not guarantee tender completeness." }),
        ]),
        new Table({
          rows,
          width: { size: 100, type: WidthType.PERCENTAGE },
          columnWidths: (() => {
            const weights = exportColumns.map((column) => {
              if (column.role === "heading") return 1.35;
              if (column.role === "requirement") return 3.4;
              if (column.role === "page" || column.role === "response") return 1;
              const sourceRole = column.sourceIndex === undefined ? undefined : sourceColumns[column.sourceIndex]?.role;
              if (sourceRole === "serial") return 0.55;
              if (sourceRole === "quantity") return 0.65;
              if (sourceRole === "compliance") return 0.85;
              if (sourceRole === "remark" || sourceRole === "deviation") return 1.45;
              return 1;
            });
            const sum = weights.reduce((total, weight) => total + weight, 0);
            const availableWidth = exportColumns.length > 4 ? 15_200 : 10_400;
            const widths = weights.map((weight) => Math.floor(availableWidth * weight / sum));
            widths[widths.length - 1] += availableWidth - widths.reduce((total, width) => total + width, 0);
            return widths;
          })(),
        }),
      ];
      const documentSections = [{
        properties: complianceSheet
          ? { page: { size: { width: 11_910, height: 16_840 }, margin: { top: 1_060, right: 425, bottom: 1_200, left: 850, header: 0, footer: 1_618 } } }
          : { page: { size: exportColumns.length > 4 ? { width: 16_840, height: 11_910 } : { width: 11_910, height: 16_840 }, margin: { top: 720, right: 700, bottom: 720, left: 700 } } },
        children: commonContent,
      }];
      const doc = new Document({
        ...(complianceSheet ? { styles: {
          default: { document: { run: { font: "Times New Roman", size: 22 } } },
          paragraphStyles: [{
            id: "TableParagraph",
            name: "Table Paragraph",
            basedOn: "Normal",
            paragraph: { spacing: { line: 224, lineRule: "exact" } },
          }],
        } } : {}),
        sections: documentSections,
      });
      const blob = await Packer.toBlob(doc);
      downloadBlob(blob, `${analysis.filename.replace(/\.pdf$/i, "")}-technical-response.docx`);
    } catch {
      setError("The response sheet could not be created. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  async function exportExcel() {
    if (!analysis || !responseSheet?.rows.length) return;
    setExporting(true);
    setError(null);
    try {
      if (responseSheet.layout === "sectioned" || responseSheet.rows.some(row => row.section)) {
        const { createSectionedWorkbook } = await import("./sectioned-exports");
        const buffer = await createSectionedWorkbook(responseSheet).xlsx.writeBuffer();
        downloadBlob(new Blob([buffer as BlobPart], {type:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}), `${analysis.filename.replace(/\.pdf$/i, "")}-technical-response.xlsx`);
        return;
      }

      const ExcelJS = await import("exceljs");
      const workbook = new ExcelJS.Workbook();
      const worksheet = workbook.addWorksheet("Technical response", { views: [{ state: "frozen", ySplit: 1 }] });
      worksheet.columns = responseSheet.columns.map((column) => ({
        header: column.header,
        key: column.header,
        width: column.role === "requirement" ? 58 : column.role === "heading" ? 32 : column.role === "page" ? 16 : 24,
      }));
      worksheet.addRows(responseSheet.rows.map((row) => row.values));
      worksheet.getRow(1).font = { bold: true, color: { argb: "FF24354D" } };
      worksheet.getRow(1).fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFEFF3F8" } };
      worksheet.eachRow((row) => {
        row.alignment = { vertical: "top", wrapText: true };
        row.font = { ...row.font, name: "Arial", size: 10 };
      });
      worksheet.getRow(1).font = { bold: true, name: "Arial", size: 10, color: { argb: "FF24354D" } };
      const headingColumns = responseSheet.columns
        .map((column, idx) => (column.role === "heading" ? idx : -1))
        .filter((idx) => idx >= 0);
      for (const headingColumn of headingColumns) {
        const colValues = responseSheet.rows.map((r) => r.values[headingColumn]);
        responseSheet.rows.forEach((row, index) => {
          if (verticalMergeAt(colValues, index) !== "restart") return;
          let end = index;
          while (end + 1 < colValues.length && colValues[end + 1] === colValues[index]) end += 1;
          if (end > index) worksheet.mergeCells(index + 2, headingColumn + 1, end + 2, headingColumn + 1);
        });
      }
      const buffer = await workbook.xlsx.writeBuffer();
      downloadBlob(new Blob([buffer as BlobPart], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), `${analysis.filename.replace(/\.pdf$/i, "")}-technical-response.xlsx`);
    } catch {
      setError("The Excel workbook could not be created. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  async function exportPdf() {
    if (!analysis || !responseSheet?.rows.length) return;
    setExporting(true);
    setError(null);
    try {
      const [{ createResponsePdf }, fontResponse] = await Promise.all([
        import("./pdf-export"), fetch("/fonts/DejaVuSans.ttf"),
      ]);
      if (!fontResponse.ok) throw new Error("The PDF font could not be loaded. Retry or download DOCX or Excel.");
      const fontBytes = new Uint8Array(await fontResponse.arrayBuffer());
      let binary = "";
      for (let offset = 0; offset < fontBytes.length; offset += 8_192) {
        binary += String.fromCharCode(...fontBytes.subarray(offset, offset + 8_192));
      }
      const pdf = createResponsePdf(responseSheet, analysis.sheetTitle || "Tender Technical Requirements", analysis.filename, btoa(binary));
      pdf.save(`${analysis.filename.replace(/\.pdf$/i, "")}-technical-response.pdf`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The PDF could not be created. Please try again.");
    } finally {
      setExporting(false);
    }
  }

  if (!analysis && !startAtUpload && !pendingResume) {
    return (
      <main ref={motionRoot} className={`tender-mvp-root mvp-landing ${startAtUpload ? "mvp-new-page" : ""}`}>
        <header className="mvp-topbar mvp-landing-topbar">
          <a className="mvp-brand" href="#top" aria-label="Tender Review home"><span className="mvp-brand-mark"><TenderReviewMark /></span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Technical response workspace</small></span></a>
          <nav className="mvp-landing-nav" aria-label="Main navigation"><a href="#product">The product</a><a href="#how-it-works">How it works</a><a href="#limits">What to expect</a><button type="button" className="mvp-text-button" onClick={openResumeSessionDialog}>Resume saved review</button></nav>
          <a className="mvp-topbar-cta" href="/new">Start a review <ArrowUpRight size={15} /></a>
        </header>
        <section className="mvp-landing-hero mvp-motion-section" id="top">
          <div className="mvp-hero-copy">
            <h1>Review the source.<br />Then respond.</h1>
            <p className="mvp-lede">Tender Review turns a technical tender PDF into a source-cited requirement list and an editable response sheet. Open each quote beside its original page, check the highlight, then export.</p>
            <div className="mvp-hero-links"><a className="mvp-primary mvp-hero-primary" href="/new">Start with a tender PDF <ArrowRight size={17} /></a><a className="mvp-secondary-link" href="#how-it-works">How it works <ArrowDownToLine size={15} /></a></div>
            <p className="mvp-hero-note"><ShieldCheck size={17} /><span><strong>You confirm each requirement.</strong><small>Rows are never marked checked automatically.</small></span></p>
          </div>
          <div className="mvp-product-shot" id="product">
            <div className="mvp-product-shot-label"><span>Tender review workspace</span><div className="mvp-shot-switch" role="group" aria-label="Choose a product view"><button type="button" aria-pressed={!showSourceDetail} onClick={() => setShowSourceDetail(false)}>Review list</button><button type="button" aria-pressed={showSourceDetail} onClick={() => setShowSourceDetail(true)}>Source highlight</button></div></div>
            <img src={showSourceDetail ? "/images/source-evidence-detail.png" : "/images/review-workspace.png"} alt={showSourceDetail ? "Original tender page with a bounding box around the selected source requirement and its exact quote" : "Tender Review workspace showing requirements beside the cited tender page with the selected source text highlighted"} />
            <div className="mvp-shot-caption"><FileText size={16} /><span><strong>{showSourceDetail ? "The citation opens at its source." : "Each requirement stays beside its source."}</strong><small>{showSourceDetail ? "Page number, exact quote and bounding box are visible together." : "Select a row to inspect the cited page and matching highlight."}</small></span></div>
          </div>
        </section>
        <section className="mvp-proof-strip mvp-motion-section" aria-label="What you can verify">
          <div><span><strong>Requirement quote</strong><small>Matched to selectable text in the PDF</small></span></div>
          <div><span><strong>Cited tender page</strong><small>With a bounding-box highlight when available</small></span></div>
          <div><span><strong>Your review decision</strong><small>Checked only after you confirm it</small></span></div>
        </section>
        <section className="mvp-evidence-showcase mvp-motion-section" id="evidence">
          <div className="mvp-evidence-showcase-copy">
            <h2>Trace every quote to the page.</h2>
            <p>Select a row to open its cited page. When the PDF text gives an exact location, a bounding box marks the matching words. The source quote stays visible while you check it.</p>
            <div className="mvp-evidence-points"><span><Check size={15} /> Cited page shown beside the review list</span><span><Check size={15} /> Quote and page highlight stay together</span><span><Check size={15} /> You decide when a row is checked</span></div>
          </div>
          <figure className="mvp-detail-shot">
            <figcaption><span>Example review · page 8</span><span><span className="mvp-detail-dot" /> Source highlight</span></figcaption>
            <img src="/images/source-evidence-detail.png" alt="Example Tender Review citation detail: page 8 of the original tender, the selected requirement highlighted on the page, and the exact source quote below" />
          </figure>
        </section>
        <section className="mvp-start-section mvp-motion-section" id="how-it-works">
          <div className="mvp-start-copy">
            <h2>Tender PDF to response sheet.</h2>
            <div className="mvp-step-list">
              <div><p><strong>Choose a tender PDF</strong><small>Use a text-based PDF up to {CLIENT_MAX_FILE_MEGABYTES} MB and 120 pages.</small></p></div>
              <div><p><strong>Verify the citations</strong><small>Open the cited page and check the quote and highlight.</small></p></div>
              <div><p><strong>Mark rows you checked</strong><small>Keep review decisions visible as you work.</small></p></div>
              <div><p><strong>Download your response sheet</strong><small>Get a DOCX with source pages and blank OEM response fields.</small></p></div>
            </div>
          </div>
          <div className="mvp-feature-card">
            <h3>What you get</h3>
            <div><FileCheck2 size={18} /><span><strong>Source-linked requirement list</strong><small>Open each row at its cited tender page.</small></span></div>
            <div><ScanSearch size={18} /><span><strong>Visible text highlights</strong><small>Bounding boxes appear when an exact location is available.</small></span></div>
            <div><ArrowDownToLine size={18} /><span><strong>Editable response sheet</strong><small>DOCX keeps OEM response cells blank for your team.</small></span></div>
            <a className="mvp-primary mvp-feature-cta" href="/new">Start a review <ArrowRight size={16} /></a>
          </div>
        </section>
        <section className="mvp-limits mvp-motion-section" id="limits">
          <div><h2>What this version supports</h2></div>
          <p>It processes text-based PDFs in this browser session. The local app can OCR scanned pages when Tesseract 5 and the selected language data are installed; the hosted preview does not include OCR tools. OCR-derived wording needs visual review. Extracted rows are a review starting point, not a guarantee that every tender requirement was found. Always check the tender source before relying on the response sheet.</p>
        </section>
        <section className="mvp-bottom-cta mvp-motion-section"><div><h2>Start with your tender PDF.</h2></div><a className="mvp-primary" href="/new">Start a review <ArrowRight size={17} /></a></section>
        <footer className="mvp-landing-footer"><span>Tender Review</span><span>Your document and review marks stay in this browser session unless you download an encrypted review file.</span></footer>
        {reviewSessionDialogs}
      </main>
    );
  }

  if (!analysis) {
    return (
      <main ref={motionRoot} className="tender-mvp-root mvp-upload-screen">
        <header className="mvp-topbar mvp-review-topbar">
          <a className="mvp-brand" href="/" aria-label="Return to Tender Review home"><span className="mvp-brand-mark"><TenderReviewMark /></span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Start a review</small></span></a>
          <div className="mvp-sheet-heading-actions"><button type="button" className="mvp-text-button" onClick={openResumeSessionDialog}>Resume saved review</button><a className="mvp-upload-back" href="/">Back to overview</a></div>
        </header>
        <section className="mvp-upload-page">
          <div className="mvp-upload-intro"><div className="mvp-eyebrow"><span className="mvp-eyebrow-mark" /> STEP 1 OF 3</div><h1>{pendingResume ? "Restore your saved review." : "Start with the tender document."}</h1><p>{pendingResume ? `Select the exact original PDF for ${pendingResume.filename}. The source is checked before its citations and reviewer changes are restored.` : "Choose a PDF. Tender Review will find requirement quotes, check them against the cited page, and show you the matching source."}</p><ul><li>PDF only · maximum {CLIENT_MAX_FILE_MEGABYTES} MB</li><li>Up to 120 pages</li><li>{pendingResume ? "The document fingerprint must match the encrypted session." : "Local OCR needs Tesseract 5 and its language data; hosted OCR is unavailable"}</li></ul></div>
          <div className="mvp-upload-card">
            <div className="mvp-upload-card-heading"><span className="mvp-upload-step">{pendingResume ? "VERIFY ORIGINAL SOURCE" : "SELECT YOUR TENDER"}</span></div>
            <form onSubmit={analyze}>
              <label className={`mvp-dropzone ${file ? "is-ready" : ""}`} htmlFor="tender-file">
                <input id="tender-file" type="file" accept="application/pdf,.pdf" onChange={pendingResume ? resumeSourceFile : selectFile} disabled={busy || sessionBusy} />
                <span className="mvp-upload-icon"><Upload size={20} /></span>
                {file ? <><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · ready to review</span></> : <><strong>{pendingResume ? "Choose the original tender PDF" : "Choose a tender PDF"}</strong><span>{pendingResume ? "It must match the saved SHA-256 fingerprint" : `PDF files up to ${CLIENT_MAX_FILE_MEGABYTES} MB`}</span></>}
                <span className="mvp-browse-link">{pendingResume ? "Verify PDF" : "Select PDF"} <ArrowUpRight size={14} /></span>
              </label>
              {pendingResume ? <button type="button" className="mvp-text-button" disabled={sessionBusy} onClick={() => { setPendingResume(null); setError(null); }}>Cancel session restore</button> : <button className="mvp-primary mvp-submit" type="submit" disabled={!file || busy}>
                {busy ? <><LoaderCircle className="mvp-spin" size={17} /> Processing tender…</> : <>{error || processing?.stage === "cancelled" ? "Try again" : "Find requirements"} <ArrowRight size={17} />
                </>}
              </button>}
              {busy && processing && <section className="mvp-processing" role="region" aria-label="Tender processing progress">
                <div className="mvp-processing-heading"><LoaderCircle className="mvp-spin" size={17} /><div><strong role="status" aria-live="polite">{processing.message}</strong><span>Long tenders can take several minutes. Keep this page open; progress updates as each step finishes.</span><span>{formatElapsedSeconds(elapsedSeconds)} elapsed{processing.current !== undefined && processing.total !== undefined ? ` · ${processing.current} of ${processing.total}` : ""}</span></div></div>
                <ol className="mvp-processing-steps">
                  {PROCESSING_STEPS.map((step, index) => {
                    const current = processingStepIndex(processing.stage);
                    const state = index < current ? "complete" : index === current ? "active" : "waiting";
                    return <li key={step.id} className={`is-${state}`} aria-current={state === "active" ? "step" : undefined}>
                      <span>{state === "complete" ? "✓" : state === "active" ? <LoaderCircle className="mvp-spin" size={14} /> : index + 1}</span>
                      <span>{step.label}</span>
                    </li>;
                  })}
                </ol>
                <button type="button" className="mvp-text-button" onClick={cancelAnalysis}>Cancel processing</button>
              </section>}
              {!busy && processing?.stage === "cancelled" && <p className="mvp-processing-terminal" role="status">{processing.message}</p>}
              {!busy && processing?.stage === "error" && <p className="mvp-processing-terminal" role="status">{processing.message}</p>}
              {error && <p className="mvp-error" role="alert">{error}</p>}
              {failureDiagnostics && <section className="mvp-coverage-failure" aria-label="Rejected extraction suggestions">
                <h2>{failureDiagnostics.classificationReviewCandidates.length > 0 ? "Grounded candidates need classification review" : "No verified requirements to review"}</h2>
                <p>{failureDiagnostics.classificationReviewCandidates.length > 0
                  ? `${failureDiagnostics.classificationReviewCandidates.length} source-grounded candidate(s) remain available for classification review and were not added as compliance obligations.`
                  : failureDiagnostics.candidateSuggestions > 0
                  ? `${failureDiagnostics.rejectedCandidates} suggestion(s) were left out because source evidence could not be verified in this ${failureDiagnostics.pageCount}-page tender. These are unverified model suggestions, not review rows. Inspect the source before relying on any wording.`
                  : `No requirement suggestions were produced for the selected pages in this ${failureDiagnostics.pageCount}-page tender. An empty extraction does not establish that the tender has no requirements; inspect the selected pages manually.`}</p>
                <dl>
                  <div><dt>Technical pages selected</dt><dd>{failureDiagnostics.coverageSummary.selectedTechnicalPages}</dd></div>
                  <div><dt>Page audits</dt><dd>{failureDiagnostics.coverageSummary.auditPagesWithNoGapsReported} reported no gaps · {failureDiagnostics.coverageSummary.auditPagesWithPossibleGaps} reported possible gaps · {failureDiagnostics.coverageSummary.auditPagesIncomplete} incomplete · {failureDiagnostics.coverageSummary.auditPagesNotRun} not run</dd></div>
                  {failureDiagnostics.coverageSummary.possibleOmissionSuggestions > 0 && <div><dt>Possible omissions</dt><dd>{failureDiagnostics.coverageSummary.possibleOmissionSuggestions} advisory suggestion(s); not a completeness measure</dd></div>}
                </dl>
                {failureDiagnostics.classificationReviewCandidates.length > 0 && <div className="mvp-coverage-row-findings">
                  <strong>Grounded candidates held for classification review</strong>
                  {failureDiagnostics.classificationReviewCandidates.map((candidate, index) => <div className="mvp-coverage-row-finding" key={`${candidate.page}-${candidate.candidateId ?? index}`}>
                    <span className="is-warning">Original classification: {candidate.originalClassification} · effective classification: {candidate.effectiveClassification} · {candidate.reason.replaceAll("_", " ")}. Not included in the compliance matrix.</span>
                    <p>{candidate.quote}</p>
                    <div className="mvp-banner-held-actions">
                      {file && <button type="button" onClick={() => { setPage(candidate.page); setSourceOpen(true); }}>Inspect PDF page {candidate.page}</button>}
                      <button type="button" className="mvp-candidate-promote-btn" onClick={() => handlePromoteFromDiagnostics(candidate, index)}>Promote to response sheet</button>
                    </div>
                  </div>)}
                </div>}
                {failureDiagnostics.rejectedSuggestionDetails.length > 0 && <ul>
                  {failureDiagnostics.rejectedSuggestionDetails.map((suggestion, index) => <li key={`${suggestion.page}-${suggestion.reason}-${index}`}>
                    <p>{suggestion.quotePreview ? `Suggested wording: “${suggestion.quotePreview}”` : "No usable wording was returned."}</p>
                    <span>{describeRejectedSuggestion(suggestion.reason)}</span>
                    {suggestion.page !== null && file && <button type="button" onClick={() => { setPage(suggestion.page!); setSourceOpen(true); }}>Inspect PDF page {suggestion.page}</button>}
                    {suggestion.page === null && <span>Source page unavailable; inspect the tender manually.</span>}
                  </li>)}
                </ul>}
                {failureDiagnostics.rejectedSuggestionsNotShown > 0 && <p>{failureDiagnostics.rejectedSuggestionsNotShown} additional rejected suggestions are summarized in the coverage count but not listed here.</p>}
                {failureDiagnostics.candidateSuggestions === 0 && failureDiagnostics.reviewPageNumbers.length > 0 && <div className="mvp-coverage-review-pages"><strong>Source pages to inspect</strong><div>{failureDiagnostics.reviewPageNumbers.map((sourcePage) => <button type="button" key={sourcePage} onClick={() => { setPage(sourcePage); setSourceOpen(true); }}>Inspect PDF page {sourcePage}</button>)}</div>{failureDiagnostics.reviewPagesNotShown > 0 && <span>{failureDiagnostics.reviewPagesNotShown} additional pages are not listed.</span>}</div>}
              </section>}
            </form>
            <div className="mvp-upload-limits"><span><FileCheck2 size={15} /> Review every quote</span><span><ShieldCheck size={15} /> Nothing marked checked for you</span></div>
          </div>
        </section>
        {failureDiagnostics && sourceOpen && file && <dialog ref={sourceDrawerRef} className="mvp-source-drawer" aria-label={`PDF page ${page} for rejected suggestion`} onClose={() => setSourceOpen(false)} onClick={(event) => { if (event.target === event.currentTarget) sourceDrawerRef.current?.close(); }}>
          <section className="mvp-evidence-panel"><div className="mvp-evidence-heading"><div><span className="mvp-panel-kicker">SOURCE REVIEW</span><h2>PDF page {page}</h2></div><button type="button" className="mvp-icon-button" aria-label="Close source page" onClick={() => sourceDrawerRef.current?.close()}><X size={18} /></button></div>
            <PdfEvidenceViewer file={file} pageNumber={page} onPageChange={(newPage) => setPage(newPage)} selectedBox={null} highlightLabel="Inspect this original page; no candidate highlight was verified" />
            <p className="mvp-review-note">No response-sheet row was created for the rejected suggestion. Review the page manually to decide whether it contains a requirement.</p>
          </section>
        </dialog>}
        <footer className="mvp-landing-footer"><span>Tender Review</span><span>Review the cited source before relying on any extracted requirement.</span></footer>
        {reviewSessionDialogs}
      </main>
    );
  }

  const reviewableRequirements = analysis.requirements.filter(item => item.rowType !== "section" && item.rowType !== "optional_heading");
  const checkedCount = reviewableRequirements.filter((item) => item.reviewed).length;
  const unreviewedCount = reviewableRequirements.filter((item) => !item.reviewed).length;
  const heldCandidatesCount = analysis.classificationReviewCandidates?.length ?? 0;
  const totalPendingHumanReview = unreviewedCount + heldCandidatesCount;

  const unresolvedAuditCount = analysis.coverage?.summary.auditPagesIncomplete ?? 0;
  const possibleGapsCount = analysis.coverage?.summary.auditPagesWithPossibleGaps ?? 0;
  const uncertainRoutingCount = analysis.coverage?.summary.routingPagesUncertain ?? 0;
  const unmappedTableRowsCount = analysis.coverage?.summary.tableRowsUnmapped ?? 0;
  const clippedRoutingCount = analysis.coverage?.summary.clippedRoutingPages ?? 0;
  const scheduleDuplicates = responseSheet ? detectScheduleDuplicates(responseSheet) : [];
  const hasUnresolvedIssues = unresolvedAuditCount > 0 || possibleGapsCount > 0 || uncertainRoutingCount > 0 || unmappedTableRowsCount > 0 || clippedRoutingCount > 0 || heldCandidatesCount > 0 || scheduleDuplicates.length > 0;

  const coveragePagesToShow = analysis.coverage?.pages.filter((item) => item.selectedForExtraction
    || item.routingDisposition !== "selected"
    || item.routerMarkedUncertain
    || item.hasRasterImageContent
    || item.imageRegions.length > 0
    || item.ocrNeeded
    || item.routingContextClipped
    || item.extractionStatus === "incomplete"
    || item.auditStatus === "incomplete"
    || item.auditStatus === "possible_gaps_reported"
    || item.rejectedSuggestions > 0
    || Boolean(item.sourceTableRowsUnmapped)) ?? [];
  const pendingReviewByPage = new Map<number, number>();
  for (const item of reviewableRequirements) {
    if (!item.reviewed) pendingReviewByPage.set(item.page, (pendingReviewByPage.get(item.page) ?? 0) + 1);
  }
  const currentNeedsReviewCount = [...pendingReviewByPage.values()].reduce((total, count) => total + count, 0);
  const currentPageCoverage = analysis.coverage?.pages.find((item) => item.page === page);
  const currentPageImageRegions = currentPageCoverage?.imageRegions ?? [];
  return (
    <main ref={motionRoot} className="tender-mvp-root mvp-review-screen">
      <header className="mvp-topbar mvp-review-topbar">
        <a className="mvp-brand" href="/" aria-label="Start a new tender"><span className="mvp-brand-mark"><TenderReviewMark /></span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Review workspace</small></span></a>
        <div className="mvp-sheet-heading-actions"><button type="button" className="mvp-text-button" onClick={openSaveSessionDialog} disabled={Boolean(productFile || productDoc || complianceReport)} title={productFile || productDoc || complianceReport ? "Portable sessions currently support the Phase 1 tender review only." : "Download an encrypted review file"}><Save size={15} /> Save review</button><button type="button" className="mvp-text-button" onClick={openResumeSessionDialog}><FolderOpen size={15} /> Resume saved</button></div>
        <div className="mvp-topbar-right"><span className="mvp-file-name"><FileText size={15} />{analysis.filename}</span></div>
      </header>
      <section className="mvp-review-summarybar">
        <div className="mvp-review-title"><div className="mvp-eyebrow">TENDER REVIEW</div><h1>Technical requirements</h1><p>Review each extracted quote against its original page before you export.</p>{processing?.stage === "complete" && <p role="status">{processing.message}</p>}</div>
        <div className="mvp-review-stats" aria-label="Tender review summary">
          <div><span className="mvp-stat-icon"><FileCheck2 size={15} /></span><span><strong>{reviewableRequirements.length}</strong><small>Source requirements</small></span></div>
          {analysis.validationSummary && (
            <div><span className="mvp-stat-icon"><ShieldCheck size={15} /></span><span><strong>{analysis.validationSummary.verbatimPass + analysis.validationSummary.visualPass}<i> / {analysis.validationSummary.total}</i></strong><small>Tier 1/2 verified</small></span></div>
          )}
          <div><span className="mvp-stat-icon mvp-stat-icon-warn"><AlertTriangle size={15} /></span><span><strong>{totalPendingHumanReview}</strong><small>Pending review ({unreviewedCount} reqs{heldCandidatesCount > 0 ? ` + ${heldCandidatesCount} held` : ""})</small></span></div>
          {heldCandidatesCount > 0 && (
            <div><span className="mvp-stat-icon mvp-stat-icon-warn"><ScanSearch size={15} /></span><span><strong>{heldCandidatesCount}</strong><small>Held for classification</small></span></div>
          )}
          <div><span className="mvp-stat-icon mvp-stat-icon-warn"><Check size={15} /></span><span><strong>{checkedCount}<i> / {reviewableRequirements.length}</i></strong><small>Checked by you</small></span></div>
          <div><span className="mvp-stat-icon"><FileText size={15} /></span><span><strong>{analysis.pageCount}</strong><small>Tender pages</small></span></div>
        </div>
      </section>
      {hasUnresolvedIssues && (
        <section className="mvp-unresolved-banner" role="alert" aria-label="Unresolved coverage and incomplete audits">
          <div className="mvp-unresolved-banner-header">
            <span className="mvp-banner-icon"><AlertTriangle size={20} /></span>
            <div>
              <strong>Incomplete AI Draft — Unresolved Coverage & Audits Require Review</strong>
              <p>This draft is not guaranteed complete. The parser/router reported unresolved pages, incomplete audits, or unclassified candidate obligations that require human inspection.</p>
            </div>
          </div>
          <div className="mvp-unresolved-banner-pills">
            {heldCandidatesCount > 0 && (
              <span className="mvp-banner-pill is-warning">
                <strong>{heldCandidatesCount}</strong> held candidate{heldCandidatesCount === 1 ? "" : "s"} await classification
              </span>
            )}
            {unresolvedAuditCount > 0 && (
              <span className="mvp-banner-pill is-warning">
                <strong>{unresolvedAuditCount}</strong> page audit{unresolvedAuditCount === 1 ? "" : "s"} incomplete
              </span>
            )}
            {possibleGapsCount > 0 && (
              <span className="mvp-banner-pill is-warning">
                <strong>{possibleGapsCount}</strong> page{possibleGapsCount === 1 ? "" : "s"} with possible omissions
              </span>
            )}
            {uncertainRoutingCount > 0 && (
              <span className="mvp-banner-pill">
                <strong>{uncertainRoutingCount}</strong> router-uncertain page{uncertainRoutingCount === 1 ? "" : "s"}
              </span>
            )}
            {unmappedTableRowsCount > 0 && (
              <span className="mvp-banner-pill">
                <strong>{unmappedTableRowsCount}</strong> unmapped table row{unmappedTableRowsCount === 1 ? "" : "s"}
              </span>
            )}
            {clippedRoutingCount > 0 && (
              <span className="mvp-banner-pill">
                <strong>{clippedRoutingCount}</strong> clipped router page{clippedRoutingCount === 1 ? "" : "s"}
              </span>
            )}
            {scheduleDuplicates.length > 0 && (
              <span className="mvp-banner-pill is-warning">
                <strong>{scheduleDuplicates.length}</strong> duplicate schedule specification{scheduleDuplicates.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
          {heldCandidatesCount > 0 && (
            <div className="mvp-banner-held-candidates">
              <div className="mvp-banner-held-heading">
                <span>Grounded candidates held for classification review (not in compliance sheet):</span>
              </div>
              <div className="mvp-banner-held-list">
                {analysis.classificationReviewCandidates?.map((candidate, idx) => (
                  <div key={`${candidate.page}-${candidate.candidateId ?? idx}`} className="mvp-banner-held-item">
                    <div className="mvp-banner-held-meta">
                      <span>Page {candidate.page} · {candidate.reason.replaceAll("_", " ")}</span>
                      <div className="mvp-banner-held-actions">
                        <button type="button" className="mvp-candidate-inspect-btn" onClick={() => { setCoverageFocus(null); setPage(candidate.page); setSourceOpen(true); }}>Inspect p. {candidate.page}</button>
                        <button type="button" className="mvp-candidate-promote-btn" onClick={() => handlePromoteCandidate(candidate, idx)}>Promote to sheet</button>
                      </div>
                    </div>
                    <p className="mvp-banner-held-quote">“{candidate.quote}”</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
      {responseSheet && <section className="mvp-sheet-panel" aria-label="Editable response sheet">
        <div className="mvp-compliance-panel">
          <div className="mvp-compliance-header">
            <div>
              <span className="mvp-compliance-kicker">PHASE 2 · OEM COMPLIANCE ENGINE</span>
              <h3>Automated Technical Compliance & Evidence Grounding</h3>
              <p>
                Compare extracted tender obligations against OEM product documentation. The engine verifies numerical tolerances, ranges, and mandatory deliverables, grounding every status in verifiable source citations.
              </p>
            </div>
            <div className="mvp-compliance-actions">
              <input
                type="file"
                id="oem-product-upload"
                accept=".pdf"
                className="mvp-compliance-file-input"
                onChange={handleProductFileUpload}
              />
              <label htmlFor="oem-product-upload" className="mvp-btn-oem-upload">
                <Upload size={14} /> {productFile ? productFile.name : "Upload OEM Product PDF"}
              </label>
              {!productFile && (
                <button
                  type="button"
                  className="mvp-btn-sample-oem"
                  onClick={handleLoadSampleProduct}
                >
                  Use Sample Salinometer OEM Datasheet
                </button>
              )}
              <button
                type="button"
                className="mvp-btn-run-compliance"
                disabled={Boolean(complianceProgressStage)}
                onClick={handleRunCompliance}
              >
                {complianceProgressStage ? (
                  <><LoaderCircle size={14} className="mvp-spin" /> {complianceProgressStage}</>
                ) : (
                  <><ShieldCheck size={15} /> Okay, it&apos;s go — Run Compliance Engine</>
                )}
              </button>
            </div>
          </div>
          {complianceReport && (
            <div className="mvp-compliance-summary-bar">
              <span className="mvp-compliance-stat">
                <strong>{complianceReport.summary.totalRows}</strong> Total Rows
              </span>
              <span className="mvp-compliance-stat is-complied">
                <Check size={14} /> <strong>{complianceReport.summary.complied}</strong> Complied
              </span>
              {complianceReport.summary.deviation > 0 && (
                <span className="mvp-compliance-stat is-deviation">
                  <AlertTriangle size={14} /> <strong>{complianceReport.summary.deviation}</strong> Deviations
                </span>
              )}
              {complianceReport.summary.needsReview + complianceReport.summary.insufficientEvidence > 0 && (
                <span className="mvp-compliance-stat is-review">
                  <ScanSearch size={14} /> <strong>{complianceReport.summary.needsReview + complianceReport.summary.insufficientEvidence}</strong> Needs Operator Review
                </span>
              )}
              {complianceReport.summary.notComplied > 0 && (
                <span className="mvp-compliance-stat is-not-complied">
                  <X size={14} /> <strong>{complianceReport.summary.notComplied}</strong> Not Complied
                </span>
              )}
            </div>
          )}
        </div>
        <div className="mvp-sheet-heading">
          <div><span className="mvp-panel-kicker">EXPORT PREVIEW</span><h2>Response sheet <span>{responseSheet.rows.length} rows</span></h2><p>Edit the sheet before downloading. Click a citation to inspect the original page and highlighted source. Sheet edits apply to all downloads.</p></div>
          <div className="mvp-sheet-heading-actions"><button type="button" className="mvp-text-button mvp-add-row-action" onClick={() => { setFormError(null); setNewReqPage(page || 1); setAddRequirementOpen(true); }}><Plus size={14} /> Add requirement</button>{scheduleDuplicates.length > 0 && <button type="button" className="mvp-text-button mvp-reconcile-action" onClick={handleReconcileDuplicates} title="Reconcile identical technical specifications repeated across bidder schedule and specification annexure"><Check size={14} /> Reconcile {scheduleDuplicates.length} duplicates</button>}{sheetEdited && <button type="button" className="mvp-text-button mvp-sheet-reset" onClick={resetResponseSheet}>Reset sheet edits</button>}<button type="button" className="mvp-text-button mvp-sheet-reset" onClick={() => { setAnalysis(null); setResponseSheet(null); setSheetEdited(false); setFile(null); setError(null); setProcessing(null); setSourceOpen(false); }}>New tender</button></div>
        </div>
        <div className="mvp-sheet-scroll">
          {buildResponseSections(responseSheet, true).map((section, sectionIndex, sections) => <section className="mvp-response-section" key={section.id}>
            {section.annexure && section.annexure !== sections[sectionIndex - 1]?.annexure && <header className="mvp-response-annexure">
              <h2>{section.annexure}</h2>
              {section.titleLines.map((line, index) => <p key={index}>{line}</p>)}
            </header>}
            {section.heading && <h3>{section.heading}</h3>}
          <table className="mvp-sheet-table">
            <thead><tr>{section.columns.map((column, index) => <th data-role={column.role} key={`${column.header}-${index}`}>{column.role === "page" ? "Source" : column.header}</th>)}<th className="mvp-sheet-actions-heading">Row actions</th></tr></thead>
            <tbody>{section.rows.map((row, sectionRowIndex) => {
              const rowIndex = responseSheet.rows.findIndex(item => item.id === row.id);
              return <tr key={row.id} className={row.section ? "is-section-row" : undefined}>
                {row.values.map((value, columnIndex) => {
                  const column = section.columns[columnIndex];
                  const locked = column.role === "page";
                  const colValues = section.rows.map((r) => r.values[columnIndex]);
                  const merge = column.role === "heading" ? verticalMergeAt(colValues, sectionRowIndex) : undefined;
                  if (merge === "continue") return null;
                  let rowSpan = 1;
                  if (merge === "restart") {
                    while (sectionRowIndex + rowSpan < colValues.length && colValues[sectionRowIndex + rowSpan] === colValues[sectionRowIndex]) rowSpan += 1;
                  }
                  return <td data-role={column.role} key={`${row.id}-${columnIndex}`} rowSpan={rowSpan} className={rowSpan > 1 ? "mvp-sheet-merged-cell" : undefined}>
                    {locked ? (
                      <div className="mvp-sheet-citations">{(row.sourceRequirementIds?.length ? row.sourceRequirementIds : [row.sourceRequirementId]).map((sourceId, citationIndex) => {
                          const item = analysis.requirements.find(requirement => requirement.id === sourceId);
                          const isApprox = Boolean(item && (item.precision === "page-only" || item.sourceReference?.locationPrecision === "approximate" || (!item.bbox && !item.sourceReference?.startOffset)));
                          return item ? <button type="button" className={`mvp-sheet-source-link ${item.reviewed ? "is-checked" : ""} ${item.isOperatorAdded ? "is-operator-added" : item.isPromoted ? "is-promoted" : item.needsHumanReview || item.ocrWarning || isApprox || item.unverifiedVisualCompletion ? "is-ocr-warning" : ""}`} key={sourceId} aria-label={`View source for response row ${rowIndex + 1}, page ${item.page}, citation ${citationIndex + 1}`} title={item.isOperatorAdded ? "Operator-added requirement: verify on tender page" : item.isPromoted ? "Promoted from classification review: verify on page" : item.unverifiedVisualCompletion ? "Unverified model visual-completion suggestion is not included in the response row" : item.needsHumanReview ? "Tier 3: Unverified quote — marked for human review" : item.ocrWarning ? "Tier 2: OCR source — verify transcription" : item.precision === "page-only" ? "Text verified on page; exact highlight unavailable" : item.sourceReference?.locationPrecision === "approximate" ? "Approximate citation: exact source location unavailable; verify on page" : item.reviewed ? "Source checked" : "Tier 1: Verbatim verified source"} onClick={() => openRequirement(item)}><FileText size={12} />p. {item.page}{row.sourceRequirementIds.length > 1 && <small>· {citationIndex + 1}</small>}{item.reviewed && <Check size={12} />}{item.isOperatorAdded ? <span>OPERATOR</span> : item.isPromoted ? <span>PROMOTED</span> : item.unverifiedVisualCompletion ? <span>CHECK IMAGE</span> : item.needsHumanReview ? <span>REVIEW</span> : item.ocrWarning ? <span>OCR</span> : item.precision === "page-only" ? <span>PAGE</span> : item.sourceReference?.locationPrecision === "approximate" ? <span>APPROX</span> : null}</button> : null;
                        })}</div>
                    ) : column.role === "compliance" ? (
                      <span className={`mvp-status-badge ${value === "Complied" ? "is-complied" : value === "Deviation" ? "is-deviation" : value === "Not Complied" ? "is-not-complied" : "is-needs-review"}`}>
                        {value}
                      </span>
                    ) : column.role === "source" && complianceReport ? (
                      (() => {
                        const assess = complianceReport.assessments.find((a) => a.rowId === row.id);
                        return assess?.productCitation ? (
                          <button
                            type="button"
                            className="mvp-sheet-product-link"
                            onClick={() => openProductCitation(assess.productCitation!)}
                            title={`View specification on page ${assess.productCitation.page} of ${assess.productCitation.documentName}`}
                          >
                            <FileText size={12} /> {assess.productCitation.documentName} p. {assess.productCitation.page}
                          </button>
                        ) : (
                          <span style={{ color: "#94a3b8", fontSize: "11px" }}>No OEM citation</span>
                        );
                      })()
                    ) : (
                      <textarea
                        aria-label={`${column.header}, row ${rowIndex + 1}${rowSpan > 1 ? `, shared across ${rowSpan} rows` : ""}`}
                        rows={Math.min(4, Math.max(1, Math.ceil(value.length / (column.role === "requirement" ? 58 : 34))))}
                        value={value}
                        onChange={(event) => updateSheetCell(row.id, section.columnIndices[columnIndex], event.target.value)}
                      />
                    )}
                  </td>;
                })}
                <td className="mvp-sheet-row-actions">
                  <button type="button" className="mvp-sheet-remove" aria-label={`Remove response row ${rowIndex + 1}`} onClick={() => removeSheetRow(row.id)}><X size={15} /> Remove</button>
                </td>
              </tr>;
            })}</tbody>
          </table>
          </section>)}
          {responseSheet.rows.length === 0 && <div className="mvp-sheet-empty"><p>All rows are removed from the export preview.</p><button type="button" className="mvp-text-button" onClick={resetResponseSheet}>Restore extracted rows</button></div>}
        </div>
        <footer className="mvp-sheet-footer">
          <span>{responseSheet.rows.length} rows · {sheetEdited ? "Unsaved edits apply to all downloads" : "Ready to review and download"}</span>
          <div className="mvp-sheet-downloads">
            <button type="button" className="mvp-export" onClick={exportDocx} disabled={exporting || responseSheet.rows.length === 0}><FileText size={16} /> Download DOCX</button>
            <button type="button" className="mvp-export mvp-export-secondary" onClick={exportPdf} disabled={exporting || responseSheet.rows.length === 0}><FileText size={16} /> Download PDF</button>
            <button type="button" className="mvp-export mvp-export-secondary" onClick={exportExcel} disabled={exporting || responseSheet.rows.length === 0}><FileSpreadsheet size={16} /> Download Excel</button>
          </div>
          {error && <p className="mvp-error" role="alert">{error}</p>}
        </footer>
      </section>}
      <details className="mvp-review-context"><summary>Review notes and coverage</summary>
          <p className="mvp-review-note">{analysis.reviewNote}{analysis.extractionMode === "structured-table" ? "" : ` ${analysis.rejectedCandidates ? `${analysis.rejectedCandidates} unmatched model suggestions were left out.` : "Unmatched suggestions are left out."}`}</p>
          {analysis.coverage && <details className="mvp-coverage-ledger">
            <summary>
              <span>Coverage ledger</span>
              <small>{countLabel(analysis.coverage.summary.selectedTechnicalPages, "routed page")} · {countLabel(analysis.coverage.summary.routingPagesExplicitlyExcluded, "explicitly excluded page")} · {countLabel(analysis.coverage.summary.routingPagesUnrouted, "unresolved route")} · {countLabel(analysis.coverage.summary.sourceMatchedRequirements, "source matched requirement row")} · {countLabel(analysis.coverage.summary.rejectedSuggestions, "rejected suggestion")}</small>
            </summary>
            <p className="mvp-coverage-caveat">Counts describe what the parser, router, and page audit actually processed. A model audit reporting no gaps does not prove that the tender is complete.</p>
            {(analysis.classificationReviewCandidates?.length ?? 0) > 0 && <div className="mvp-coverage-row-findings">
              <strong>Grounded candidates held for classification review · not compliance obligations</strong>
              {analysis.classificationReviewCandidates?.map((candidate, index) => <div className="mvp-coverage-row-finding" key={`${candidate.page}-${candidate.candidateId ?? index}`}>
                <span className="is-warning">Original classification: {candidate.originalClassification} · effective classification: {candidate.effectiveClassification} · {candidate.reason.replaceAll("_", " ")}.</span>
                <p>{candidate.quote}</p>
                <div className="mvp-banner-held-actions">
                  <button type="button" onClick={() => { setCoverageFocus(null); setPage(candidate.page); setSourceOpen(true); }}>Inspect PDF page {candidate.page}</button>
                  <button type="button" className="mvp-candidate-promote-btn" onClick={() => handlePromoteCandidate(candidate, index)}>Promote to sheet</button>
                </div>
              </div>)}
            </div>}
            <dl className="mvp-coverage-summary">
              <div><dt>Source inventory</dt><dd>All {analysis.document.pageCount} physical pages and parser-owned references passed structural checks. This does not establish semantic completeness.</dd></div>
              <div><dt>Router input</dt><dd>{analysis.coverage.summary.routingPages} of {analysis.coverage.summary.documentPages} pages with native or OCR text</dd></div>
              <div><dt>Routing dispositions</dt><dd>{countLabel(analysis.coverage.summary.selectedTechnicalPages, "page")} selected · {countLabel(analysis.coverage.summary.routingPagesUncertain, "uncertain page")} · {countLabel(analysis.coverage.summary.routingPagesUnrouted, "unrouted page")} · {countLabel(analysis.coverage.summary.routingPagesWithoutText, "page without text")}</dd></div>
              <div><dt>Source table rows</dt><dd>{countLabel(analysis.coverage.summary.tableRowsDetected, "row")} detected · {countLabel(analysis.coverage.summary.tableRowsMappedToCandidates, "row")} mapped · {countLabel(analysis.coverage.summary.tableRowsExcludedAsHeaders, "header")} · {countLabel(analysis.coverage.summary.tableRowsEmpty, "empty row")} · {countLabel(analysis.coverage.summary.tableRowsUnmapped, "nonempty row")} unmapped, across {countLabel(analysis.coverage.summary.tablePagesWithKnownRowCount, "page")} with detected row geometry</dd></div>
              <div><dt>Suggestions and review</dt><dd>{countLabel(analysis.coverage.summary.candidateSuggestions, "model suggestion")} · {countLabel(analysis.coverage.summary.sourceMatchedRows, "source matched row")} including headings · {countLabel(analysis.coverage.summary.sourceMatchedRequirements, "source matched requirement row")} · {countLabel(currentNeedsReviewCount, "row")} awaiting your review</dd></div>
              <div><dt>Page audits</dt><dd>{analysis.coverage.summary.auditPagesWithNoGapsReported} reported no gaps · {analysis.coverage.summary.auditPagesWithPossibleGaps} flagged possible gaps · {analysis.coverage.summary.auditPagesIncomplete} incomplete · {analysis.coverage.summary.auditPagesNotRun} not run</dd></div>
              {analysis.coverage.summary.pagesWithoutSelectableText > 0 && <div><dt>OCR review</dt><dd>{countLabel(analysis.coverage.summary.pagesWithoutSelectableText, "page")} had no selectable text</dd></div>}
              {analysis.coverage.summary.ocrRecommendedPages > 0 && <div><dt>OCR outcomes</dt><dd>{countLabel(analysis.coverage.summary.ocrRecommendedPages, "page")} recommended · {countLabel(analysis.coverage.summary.ocrAttemptedPages, "OCR attempt")} · {countLabel(analysis.coverage.summary.ocrSkippedPages, "skip")} · {countLabel(analysis.coverage.summary.ocrFailedPages, "OCR failure")} · {countLabel(analysis.coverage.summary.ocrCompletedWithoutTextPages, "page completed without text", "pages completed without text")}</dd></div>}
              {analysis.coverage.summary.pagesProcessedWithOcr > 0 && <div><dt>Local OCR</dt><dd>{countLabel(analysis.coverage.summary.pagesProcessedWithOcr, "page")} transcribed locally; verify every OCR-grounded row against the page image</dd></div>}
              {analysis.coverage.summary.clippedRoutingPages > 0 && <div><dt>Clipped router context</dt><dd>{countLabel(analysis.coverage.summary.clippedRoutingPages, "page")} had source text outside the routing excerpt</dd></div>}
              {analysis.coverage.summary.possibleOmissionSuggestions > 0 && <div><dt>Possible omissions</dt><dd>{countLabel(analysis.coverage.summary.possibleOmissionSuggestions, "source suggestion")} returned by the page audit; inspect the flagged pages</dd></div>}
              {analysis.coverage.summary.unattributedCandidateSuggestions > 0 && <div><dt>Unattributed suggestions</dt><dd>{countLabel(analysis.coverage.summary.unattributedCandidateSuggestions, "suggestion")} had no usable source page</dd></div>}
            </dl>
            <ul className="mvp-coverage-pages">
              {coveragePagesToShow.map((item) => {
                const rejectedOnPage = (analysis.rejectedSuggestionDetails ?? []).filter((suggestion) => suggestion.page === item.page);
                const imageOcrCounts = item.imageRegions.reduce((counts, region) => {
                  counts[region.ocrDisposition] = (counts[region.ocrDisposition] ?? 0) + 1;
                  return counts;
                }, {} as Partial<Record<(typeof item.imageRegions)[number]["ocrDisposition"], number>>);
                return <li key={item.page}>
                  <div className="mvp-coverage-page-title"><strong>PDF page {item.page}</strong><button type="button" onClick={() => { setCoverageFocus(null); setPage(item.page); setSourceOpen(true); }}>Open source page</button></div>
                  <span className={item.routingDisposition === "selected" && !item.routerMarkedUncertain ? "" : "is-warning"}>Router disposition: {item.routingDisposition.replace(/_/g, " ")}{item.routerMarkedUncertain && item.routingDisposition === "selected" ? " · also marked uncertain" : ""} · {item.routingReason}</span>
                  <span>{item.ocrStatus === "text-found" ? "Local OCR produced text · verify transcription"
                    : item.ocrStatus === "no-text-found" ? "Local OCR completed without finding text"
                      : item.ocrStatus === "failed" ? "Local OCR failed"
                        : item.ocrStatus === "not-attempted" ? `OCR recommended but not attempted${item.ocrSkipReason ? ` · ${item.ocrSkipReason.replaceAll("-", " ")}` : ""}`
                          : item.hasRasterImageContent ? "Raster image present · OCR not recommended" : item.selectedForExtraction ? "Selected for extraction" : "Not selected for extraction"}</span>
                  {item.imageRegions.length > 0 && <span>{countLabel(item.imageRegions.length, "raster image region")} detected · OCR: {Object.entries(imageOcrCounts).map(([state, count]) => `${count} ${state.replaceAll("-", " ")}`).join(", ")} · bounds are approximate; inspect regions not covered by OCR</span>}
                  {item.ocrSkipReason && item.ocrStatus !== "not-attempted" && <span className="is-warning">Some image regions were not OCR processed ({item.ocrSkipReason.replaceAll("-", " ")}); inspect remaining regions.</span>}
                  {(item.ocrStatus === "not-attempted" || item.ocrStatus === "no-text-found" || item.ocrStatus === "failed") && <span className="is-warning">Check this source page visually; OCR state does not establish that the image contains no requirement.</span>}
                  {item.sourceTableRowsDetected !== null && <span>{countLabel(item.sourceTableRowsDetected, "source table row")} detected</span>}
                  {item.sourceTableRowsMappedToCandidates !== null && <span>{countLabel(item.sourceTableRowsMappedToCandidates, "row")} mapped to candidates · {countLabel(item.sourceTableRowsExcludedAsHeaders ?? 0, "header")} · {countLabel(item.sourceTableRowsEmpty ?? 0, "empty row")} · {countLabel(item.sourceTableRowsUnmapped ?? 0, "nonempty row")} unmapped</span>}
                  {Boolean(item.sourceTableCoverageRows?.length) && <div className="mvp-coverage-row-findings">
                    <strong>Detected source rows and their extraction coverage</strong>
                    {item.sourceTableCoverageRows?.slice(0, 12).map((row) => {
                      const status = row.disposition === "header" ? "repeated header"
                        : row.disposition === "empty" ? "empty row"
                          : row.disposition === "unmapped" ? "no candidate generated"
                          : `${countLabel(row.candidateSuggestions, "candidate")} · ${countLabel(row.sourceMatchedCandidates, "source-matched candidate")} · ${row.semanticCoverageStatus.replaceAll("_", " ")}`;
                      const needsInspection = row.disposition === "unmapped" || row.sourceMatchedCandidates < row.candidateSuggestions || row.semanticCoverageStatus !== "not_applicable";
                      return <div className="mvp-coverage-row-finding" key={`${item.page}-${row.rowNumber}`}>
                        <span className={needsInspection ? "is-warning" : ""}><b>Detected row {row.rowNumber}</b> · {status} · classified {row.originalSourceClassification && row.originalSourceClassification !== row.sourceClassification ? `${row.originalSourceClassification.replaceAll("_", " ")} → ` : ""}{row.sourceClassification.replaceAll("_", " ")} ({row.classificationReason.replaceAll("_", " ")}){row.textTruncated ? " · excerpt shortened" : ""}</span>
                        <p>{row.cells.filter(Boolean).join(" | ") || "(No cell text available)"}</p>
                        <button type="button" disabled={!row.bbox} onClick={() => { setCoverageFocus({ page: item.page, row }); setPage(item.page); setSourceOpen(true); }}>Inspect source row</button>
                      </div>;
                    })}
                    {Boolean(item.sourceTableRowsNotShown) && <span className="is-warning">{item.sourceTableRowsNotShown} additional detected row(s) are not listed here; inspect the full page.</span>}
                    {Boolean(item.sourceTableRowsUnmapped) && <span className="is-warning">{countLabel(item.sourceTableRowsUnmapped ?? 0, "nonempty row")} produced no extraction candidate; each needs inspection. Unmapped rows may be headings or other non-requirement content.</span>}
                  </div>}
                  <span>{item.candidateSuggestions} model suggestion(s) · {item.sourceMatchedRows} source matched row(s) · {item.sourceMatchedRequirements} requirement row(s) · {pendingReviewByPage.get(item.page) ?? 0} need review</span>
                  {item.extractionStatus === "incomplete" && <span className="is-warning">Extraction incomplete</span>}
                  {item.routingContextClipped && <span className="is-warning">Routing excerpt clipped</span>}
                  <span className={item.auditStatus === "no_gaps_reported" ? "" : "is-warning"}>Page audit: {item.auditStatus.replace(/_/g, " ")}</span>
                  {item.possibleOmissionSuggestions > 0 && <span className="is-warning">{countLabel(item.possibleOmissionSuggestions, "possible omission suggestion")}</span>}
                  {rejectedOnPage.map((suggestion, index) => <span className="mvp-coverage-rejection" key={`${item.page}-${suggestion.reason}-${index}`}>
                    {describeRejectedSuggestion(suggestion.reason)}{suggestion.quotePreview ? ` Suggested wording: “${suggestion.quotePreview}”` : ""}
                  </span>)}
                </li>;
              })}
            </ul>
            {analysis.coverage.summary.unattributedRejectedSuggestions > 0 && <p className="is-warning">{countLabel(analysis.coverage.summary.unattributedRejectedSuggestions, "rejected suggestion")} had no usable source page reference.</p>}
          </details>}
      </details>
        <dialog ref={sourceDrawerRef} className="mvp-source-drawer" aria-labelledby="source-drawer-title" onClose={() => setSourceOpen(false)} onClick={(event) => { if (event.target === event.currentTarget) sourceDrawerRef.current?.close(); }}>
        <section className="mvp-evidence-panel" aria-label="Cited source evidence">
          <div className="mvp-evidence-heading">
            <div>
              <span className="mvp-panel-kicker">{activeDrawerDoc === "tender" ? "TENDER SOURCE EVIDENCE" : "OEM PRODUCT EVIDENCE"}</span>
              <h2 id="source-drawer-title">
                {activeDrawerDoc === "tender"
                  ? coverageFocus?.page === page ? `Page ${page} source row` : sourcePageRequirement ? `Page ${page} citation` : `Page ${page} source`
                  : `Product datasheet page ${productPage}`}
              </h2>
            </div>
            <div className="mvp-evidence-actions">
              {activeDrawerDoc === "tender" ? (
                <>
                  <button className="mvp-icon-button" onClick={() => { setCoverageFocus(null); setPage((current) => Math.max(1, current - 1)); }} aria-label="Previous page" disabled={page <= 1}><ArrowLeft size={16} /></button>
                  <span><strong>{String(page).padStart(2, "0")}</strong> / {analysis.pageCount}</span>
                  <button className="mvp-icon-button" onClick={() => { setCoverageFocus(null); setPage((current) => Math.min(analysis.pageCount, current + 1)); }} aria-label="Next page" disabled={page >= analysis.pageCount}><ArrowRight size={16} /></button>
                </>
              ) : (
                <>
                  <button className="mvp-icon-button" onClick={() => setProductPage((current) => Math.max(1, current - 1))} aria-label="Previous page" disabled={productPage <= 1}><ArrowLeft size={16} /></button>
                  <span><strong>{String(productPage).padStart(2, "0")}</strong> / {productDoc?.pageCount || 3}</span>
                  <button className="mvp-icon-button" onClick={() => setProductPage((current) => Math.min(productDoc?.pageCount || 3, current + 1))} aria-label="Next page" disabled={productPage >= (productDoc?.pageCount || 3)}><ArrowRight size={16} /></button>
                </>
              )}
              <button type="button" className="mvp-icon-button" aria-label="Close source drawer" onClick={() => sourceDrawerRef.current?.close()} autoFocus><X size={18} /></button>
            </div>
          </div>
          {productDoc && (
            <div className="mvp-drawer-doc-tabs">
              <button
                type="button"
                className={`mvp-drawer-tab-btn ${activeDrawerDoc === "tender" ? "is-active" : ""}`}
                onClick={() => setActiveDrawerDoc("tender")}
              >
                Tender PDF ({file?.name || "Tender.pdf"})
              </button>
              <button
                type="button"
                className={`mvp-drawer-tab-btn ${activeDrawerDoc === "product" ? "is-active" : ""}`}
                onClick={() => setActiveDrawerDoc("product")}
              >
                OEM Product PDF ({productDoc.name})
              </button>
            </div>
          )}
          {sourceOpen && activeDrawerDoc === "tender" && file && (
            <PdfEvidenceViewer
              file={file}
              pageNumber={page}
              onPageChange={(newPage) => setPage(newPage)}
              selectedBox={coverageFocus?.page === page ? coverageFocus.row.bbox : sourcePageRequirement?.bbox ?? null}
              imageRegions={currentPageImageRegions}
              highlightLabel={
                coverageFocus?.page === page
                  ? "Detected source row not matched to an extraction candidate; inspect its meaning"
                  : sourcePageRequirement?.isOperatorAdded
                  ? "Operator-added requirement; verify against source page"
                  : sourcePageRequirement?.isPromoted
                  ? "Promoted classification candidate; verify on page"
                  : sourcePageRequirement?.ocrWarning
                  ? "Approximate table-row box for visually transcribed text; verify the full row"
                  : sourcePageRequirement?.sourceReference?.locationPrecision === "approximate" || sourcePageRequirement?.precision === "page-only"
                  ? "Approximate citation bounds; exact parser element ID not identified"
                  : sourcePageRequirement?.bbox ? "Bounding box for cited source quote" : "No verified requirement highlight is associated with this page"
              }
            />
          )}
          {sourceOpen && activeDrawerDoc === "product" && (productFile || sampleProductFileRef.current) && (
            <PdfEvidenceViewer
              file={productFile || sampleProductFileRef.current!}
              pageNumber={productPage}
              onPageChange={(newPage) => setProductPage(newPage)}
              selectedBox={productBox}
              highlightLabel="OEM product specification evidence"
            />
          )}
          {sourceOpen && activeDrawerDoc === "tender" && currentPageImageRegions.length > 0 && <p className="mvp-image-region-note">Dashed outlines mark parser-detected raster image bounds. Bounds are approximate and do not identify whether an image contains technical text.</p>}
          {sourceOpen && activeDrawerDoc === "tender" && currentPageCoverage?.hasRasterImageContent && currentPageImageRegions.length === 0 && <p className="mvp-image-region-note">Raster image content was detected, but its bounds were not resolved. Inspect this page visually.</p>}
          {activeDrawerDoc === "product" ? (
            <div className="mvp-citation-detail">
              <div className="mvp-citation-label">
                <span className="mvp-exact-dot" /> VERIFIED OEM PRODUCT CITATION · PAGE {productPage}
              </div>
              <blockquote>{productCitationEvidence?.quote || "Product specification excerpt from technical documentation."}</blockquote>
              <p style={{ margin: "4px 0 0", fontSize: "11px", color: "#64748b" }}>
                Document: {productDoc?.name} (Source Evidence)
              </p>
            </div>
          ) : (
            <div className="mvp-citation-detail">
              <div className={`mvp-citation-label ${coverageFocus?.page === page ? "" : sourcePageRequirement?.isOperatorAdded ? "is-operator-added" : sourcePageRequirement?.isPromoted ? "is-promoted" : sourcePageRequirement?.needsHumanReview || sourcePageRequirement?.ocrWarning || sourcePageRequirement?.precision === "page-only" || sourcePageRequirement?.sourceReference?.locationPrecision === "approximate" ? "is-ocr-warning" : ""}`}><span className="mvp-exact-dot" /> {coverageFocus?.page === page ? coverageRowReviewLabel(coverageFocus.row) : sourcePageRequirement?.isOperatorAdded ? "OPERATOR-ADDED REQUIREMENT · REQUIRES HUMAN CONFIRMATION" : sourcePageRequirement?.isPromoted ? "PROMOTED FROM CLASSIFICATION REVIEW · VERIFY ON PAGE" : sourcePageRequirement?.needsHumanReview ? "UNVERIFIED CITATION · REQUIRES HUMAN REVIEW" : sourcePageRequirement?.ocrWarning ? "VISUAL TRANSCRIPTION · VERIFY IN SOURCE" : sourcePageRequirement?.precision === "page-only" ? "TEXT VERIFIED · LOCATION UNCERTAIN" : sourcePageRequirement?.sourceReference?.locationPrecision === "approximate" ? "APPROXIMATE CITATION · VERIFY ON PAGE" : sourcePageRequirement?.parameter ? "SOURCE TABLE / LIST TEXT" : sourcePageRequirement ? "EXACT SOURCE QUOTE" : "SOURCE PAGE REVIEW · NO REQUIREMENT SELECTED"} <span>·</span> PAGE {String(coverageFocus?.page === page ? coverageFocus.page : page).padStart(2, "0")}{displayedCitationEvidence?.sourceElementIds.length ? <span className="mvp-source-element-ids">({countLabel(displayedCitationEvidence.sourceElementIds.length, "element")}: {displayedCitationEvidence.sourceElementIds.join(", ")})</span> : displayedCitationEvidence?.approximate ? <span className="mvp-source-element-ids">(Approximate citation)</span> : null}</div>
              <blockquote>{coverageFocus?.page === page ? coverageFocus.row.cells.filter(Boolean).join(" | ") : sourcePageRequirement?.quote ?? "No requirement quote is selected for this source page. Inspect the PDF and add a row if needed."}</blockquote>
              {coverageFocus?.page !== page && sourcePageRequirement?.selectableTextQuote && <div className="mvp-selectable-excerpt"><span>SELECTABLE PDF TEXT</span><p>{sourcePageRequirement.selectableTextQuote}</p></div>}
              {coverageFocus?.page !== page && sourcePageRequirement?.unverifiedVisualCompletion && <div className="mvp-selectable-excerpt"><span>UNVERIFIED VISUAL COMPLETION · NOT EXPORTED</span><p>{sourcePageRequirement.unverifiedVisualCompletion}</p><p>Model-proposed wording; compare it with the page image before using it.</p></div>}
              <div className="mvp-review-actions"><span>{coverageFocus?.page === page ? coverageRowReviewMessage(coverageFocus.row) : sourcePageRequirement?.isOperatorAdded ? "You added this requirement manually. Confirm the wording against the cited source page." : sourcePageRequirement?.isPromoted ? "This requirement was promoted from classification review. Confirm against the cited page." : sourcePageRequirement?.reviewed ? "You checked this citation against the page." : sourcePageRequirement?.needsHumanReview ? "This quote could not be verified automatically; inspect and verify manually against the page." : sourcePageRequirement && (sourcePageRequirement.precision === "page-only" || sourcePageRequirement.sourceReference?.locationPrecision === "approximate") ? "The citation has an approximate or unlinked location. Inspect the original page and verify the wording manually." : sourcePageRequirement?.bbox ? "Confirm the wording and highlight against the original." : sourcePageRequirement ? "Open the cited page to check the quote and source location." : "Inspect this physical page. No requirement is selected or highlighted."}</span><button disabled={Boolean(coverageFocus?.page === page) || !sourcePageRequirement} className={sourcePageRequirement?.reviewed ? "mvp-check-button is-checked" : "mvp-check-button"} onClick={markReviewed}>{coverageFocus?.page === page ? "Source row" : sourcePageRequirement?.reviewed ? <><Check size={14} /> Checked</> : "Mark checked"}</button></div>
            </div>
          )}
        </section>
      </dialog>
      {addRequirementOpen && (
        <dialog className="mvp-modal-dialog" open onClose={() => setAddRequirementOpen(false)}>
          <div className="mvp-modal-backdrop" onClick={() => setAddRequirementOpen(false)} />
          <div className="mvp-modal-content" role="dialog" aria-labelledby="add-req-title">
            <div className="mvp-modal-header">
              <div>
                <span className="mvp-panel-kicker">HUMAN OPERATOR RECOVERY</span>
                <h2 id="add-req-title">Add missing requirement</h2>
              </div>
              <button type="button" className="mvp-icon-button" aria-label="Close dialog" onClick={() => setAddRequirementOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleAddRequirement} className="mvp-modal-form">
              <p className="mvp-modal-desc">
                Manually add a requirement missed by automated extraction. It will be added to the response sheet with source page attribution and flagged for human review.
              </p>
              {formError && <p className="mvp-error" role="alert">{formError}</p>}
              <div className="mvp-form-group-row">
                <div className="mvp-form-group">
                  <label htmlFor="req-page">Source Page <span className="is-required">*</span></label>
                  <input
                    id="req-page"
                    type="number"
                    min={1}
                    max={analysis.pageCount}
                    value={newReqPage}
                    onChange={(e) => setNewReqPage(e.target.value)}
                    required
                  />
                </div>
                <div className="mvp-form-group">
                  <label htmlFor="req-category">Category</label>
                  <input
                    id="req-category"
                    type="text"
                    value={newReqCategory}
                    onChange={(e) => setNewReqCategory(e.target.value)}
                    placeholder="e.g. Technical"
                  />
                </div>
              </div>
              <div className="mvp-form-group">
                <label htmlFor="req-heading">Section / Heading <small>(optional)</small></label>
                <input
                  id="req-heading"
                  type="text"
                  value={newReqHeading}
                  onChange={(e) => setNewReqHeading(e.target.value)}
                  placeholder="e.g. Temperature Controller or 4.2 Technical Parameters"
                />
              </div>
              <div className="mvp-form-group">
                <label htmlFor="req-text">Technical Requirement Wording <span className="is-required">*</span></label>
                <textarea
                  id="req-text"
                  rows={4}
                  value={newReqText}
                  onChange={(e) => setNewReqText(e.target.value)}
                  placeholder="Enter the exact requirement wording from the source page..."
                  required
                />
              </div>
              <div className="mvp-modal-actions">
                <button type="button" className="mvp-text-button" onClick={() => setAddRequirementOpen(false)}>Cancel</button>
                <button type="submit" className="mvp-primary">Add to response sheet</button>
              </div>
            </form>
          </div>
        </dialog>
      )}
      {reviewSessionDialogs}
    </main>
  );
}
