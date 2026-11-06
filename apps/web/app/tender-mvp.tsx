"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { AlertTriangle, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, Check, FileCheck2, FileSpreadsheet, FileText, LoaderCircle, ScanSearch, ShieldCheck, Upload, X } from "lucide-react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { PdfEvidenceViewer } from "@/components/mvp/pdf-evidence-viewer";
import { PROCESSING_STEPS, formatElapsedSeconds, processingStepIndex, type ProcessingProgress } from "./processing-progress";
import { consumeAnalysisStream } from "./analysis-events";
import { prepareVisualComplianceRows } from "./visual-table";
import { complianceRowHeightTwips, reflowComplianceText, splitHeadingPrefix, verticalMergeAt } from "./compliance-format";
import { buildResponseSections } from "./response-sections";
import { buildResponseSheet, responseHeadingMergeKeys, removeResponseSheetRow, updateResponseSheetCell, splitRequirementSubpoints, type ResponseSheet } from "./response-sheet";
import type { RequirementSourceReference } from "./source-document";
import { describeRejectedSuggestion, type CoverageReport, type CoverageSourceRow, type RejectedSuggestion } from "./coverage-ledger";

gsap.registerPlugin(useGSAP, ScrollTrigger);

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
};
type Analysis = {
  filename: string;
  pageCount: number;
  textPages: number;
  document: { documentId: string; documentVersionId: string; documentFingerprint: string; pageCount: number };
  normalizedTables?: boolean;
  sectionTitle?: string;
  sectionHeading?: string;
  sourceColumns?: Array<{ header: string; role: "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other" }>;
  sheetTitle?: string;
  sheetHeading?: string;
  sheetProductTitle?: string;
  requirements: Requirement[];
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
};

function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function coverageRowReviewLabel(row: CoverageSourceRow): string {
  if (row.disposition === "header") return `SOURCE HEADER ROW ${row.rowNumber} · REPEATED LABEL`;
  if (row.disposition === "empty") return `EMPTY SOURCE ROW ${row.rowNumber}`;
  if (row.disposition === "unmapped") return `UNMAPPED SOURCE ROW ${row.rowNumber} · NEEDS INSPECTION`;
  if (row.sourceMatchedCandidates < row.candidateSuggestions) return `SOURCE ROW ${row.rowNumber} · COVERAGE MISMATCH`;
  return `SOURCE TABLE ROW ${row.rowNumber} · CANDIDATES SOURCE MATCHED`;
}

function coverageRowReviewMessage(row: CoverageSourceRow): string {
  if (row.disposition === "header") return "This detected row was classified as a repeated table header.";
  if (row.disposition === "empty") return "This detected source row contains no selectable cell text.";
  if (row.disposition === "unmapped") return "No extraction candidate was generated for this nonempty source row. Decide whether it is a requirement, heading, or other table content.";
  if (row.sourceMatchedCandidates < row.candidateSuggestions) {
    return `${row.sourceMatchedCandidates} of ${row.candidateSuggestions} generated candidates from this source row matched the source; inspect the unmatched candidate and confirm the row grouping.`;
  }
  return `${countLabel(row.candidateSuggestions, "candidate")} from this source row matched the source. Check that the extracted wording and grouping preserve the full row meaning.`;
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

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
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
    setFile(event.target.files?.[0] ?? null);
  }

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
      const result = await consumeAnalysisStream<{ ok: boolean; analysis?: Analysis; error?: string; pageCount?: number; candidateSuggestions?: number; rejectedCandidates?: number; rejectedSuggestionDetails?: RejectedSuggestion[]; rejectedSuggestionsNotShown?: number; coverageSummary?: CoverageReport["summary"]; reviewPageNumbers?: number[]; reviewPagesNotShown?: number }>(response, {
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
    setCoverageFocus(null);
    setActiveId(item.id);
    setPage(item.page);
    setSourceOpen(true);
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
    setResponseSheet(removeResponseSheetRow(responseSheet, rowId));
    setSheetEdited(true);
  }

  function resetResponseSheet() {
    if (!analysis) return;
    setResponseSheet(buildResponseSheet(analysis));
    setSheetEdited(false);
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

  if (!analysis && !startAtUpload) {
    return (
      <main ref={motionRoot} className={`tender-mvp-root mvp-landing ${startAtUpload ? "mvp-new-page" : ""}`}>
        <header className="mvp-topbar mvp-landing-topbar">
          <a className="mvp-brand" href="#top" aria-label="Tender Review home"><span className="mvp-brand-mark"><TenderReviewMark /></span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Technical response workspace</small></span></a>
          <nav className="mvp-landing-nav" aria-label="Main navigation"><a href="#product">The product</a><a href="#how-it-works">How it works</a><a href="#limits">What to expect</a></nav>
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
              <div><p><strong>Choose a tender PDF</strong><small>Use a text-based PDF up to 4 MB and 120 pages.</small></p></div>
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
        <footer className="mvp-landing-footer"><span>Tender Review <span>·</span> Single-user pilot</span><span>Your document and review marks stay in this browser session and are not saved as project history.</span></footer>
      </main>
    );
  }

  if (!analysis) {
    return (
      <main ref={motionRoot} className="tender-mvp-root mvp-upload-screen">
        <header className="mvp-topbar mvp-review-topbar">
          <a className="mvp-brand" href="/" aria-label="Return to Tender Review home"><span className="mvp-brand-mark"><TenderReviewMark /></span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Start a review</small></span></a>
          <a className="mvp-upload-back" href="/">Back to overview</a>
        </header>
        <section className="mvp-upload-page">
          <div className="mvp-upload-intro"><div className="mvp-eyebrow"><span className="mvp-eyebrow-mark" /> STEP 1 OF 3</div><h1>Start with the tender document.</h1><p>Choose a PDF. Tender Review will find requirement quotes, check them against the cited page, and show you the matching source.</p><ul><li>PDF only · maximum 32 MB locally (4 MB hosted)</li><li>Up to 120 pages</li><li>Local OCR needs Tesseract 5 and its language data; hosted OCR is unavailable</li></ul></div>
          <div className="mvp-upload-card">
            <div className="mvp-upload-card-heading"><span className="mvp-upload-step">SELECT YOUR TENDER</span><span className="mvp-upload-private"><span /> Single browser session</span></div>
            <form onSubmit={analyze}>
              <label className={`mvp-dropzone ${file ? "is-ready" : ""}`} htmlFor="tender-file">
                <input id="tender-file" type="file" accept="application/pdf,.pdf" onChange={selectFile} disabled={busy} />
                <span className="mvp-upload-icon"><Upload size={20} /></span>
                {file ? <><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · ready to review</span></> : <><strong>Choose a tender PDF</strong><span>PDF files up to 32 MB locally (4 MB hosted)</span></>}
                <span className="mvp-browse-link">Select PDF <ArrowUpRight size={14} /></span>
              </label>
              <button className="mvp-primary mvp-submit" type="submit" disabled={!file || busy}>
                {busy ? <><LoaderCircle className="mvp-spin" size={17} /> Processing tender…</> : <>{error || processing?.stage === "cancelled" ? "Try again" : "Find requirements"} <ArrowRight size={17} />
                </>}
              </button>
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
                <h2>No verified requirements to review</h2>
                <p>{failureDiagnostics.candidateSuggestions > 0
                  ? `${failureDiagnostics.rejectedCandidates} suggestion(s) were left out because source evidence could not be verified in this ${failureDiagnostics.pageCount}-page tender. These are unverified model suggestions, not review rows. Inspect the source before relying on any wording.`
                  : `No requirement suggestions were produced for the selected pages in this ${failureDiagnostics.pageCount}-page tender. An empty extraction does not establish that the tender has no requirements; inspect the selected pages manually.`}</p>
                <dl>
                  <div><dt>Technical pages selected</dt><dd>{failureDiagnostics.coverageSummary.selectedTechnicalPages}</dd></div>
                  <div><dt>Page audits</dt><dd>{failureDiagnostics.coverageSummary.auditPagesWithNoGapsReported} reported no gaps · {failureDiagnostics.coverageSummary.auditPagesWithPossibleGaps} reported possible gaps · {failureDiagnostics.coverageSummary.auditPagesIncomplete} incomplete · {failureDiagnostics.coverageSummary.auditPagesNotRun} not run</dd></div>
                  {failureDiagnostics.coverageSummary.possibleOmissionSuggestions > 0 && <div><dt>Possible omissions</dt><dd>{failureDiagnostics.coverageSummary.possibleOmissionSuggestions} advisory suggestion(s); not a completeness measure</dd></div>}
                </dl>
                {failureDiagnostics.rejectedSuggestionDetails.length > 0 && <ul>
                  {failureDiagnostics.rejectedSuggestionDetails.map((suggestion, index) => <li key={`${suggestion.page}-${suggestion.reason}-${index}`}>
                    <p>{suggestion.quotePreview ? `Suggested wording: “${suggestion.quotePreview}”` : "No usable wording was returned."}</p>
                    <span>{describeRejectedSuggestion(suggestion.reason)}</span>
                    {suggestion.page !== null && file && <button type="button" onClick={() => { setPage(suggestion.page!); setSourceOpen(true); }}>Inspect PDF page {suggestion.page}</button>}
                    {suggestion.page === null && <span>Source page unavailable; inspect the tender manually.</span>}
                  </li>)}
                </ul>}
                {failureDiagnostics.rejectedSuggestionsNotShown > 0 && <p>{failureDiagnostics.rejectedSuggestionsNotShown} additional rejected suggestions are summarized in the coverage count but not listed here.</p>}
                {failureDiagnostics.candidateSuggestions === 0 && failureDiagnostics.reviewPageNumbers.length > 0 && <div className="mvp-coverage-review-pages"><strong>Selected source pages</strong><div>{failureDiagnostics.reviewPageNumbers.map((sourcePage) => <button type="button" key={sourcePage} onClick={() => { setPage(sourcePage); setSourceOpen(true); }}>Inspect PDF page {sourcePage}</button>)}</div>{failureDiagnostics.reviewPagesNotShown > 0 && <span>{failureDiagnostics.reviewPagesNotShown} additional selected pages are not listed.</span>}</div>}
              </section>}
            </form>
            <div className="mvp-upload-limits"><span><FileCheck2 size={15} /> Review every quote</span><span><ShieldCheck size={15} /> Nothing marked checked for you</span></div>
          </div>
        </section>
        {failureDiagnostics && sourceOpen && file && <dialog ref={sourceDrawerRef} className="mvp-source-drawer" aria-label={`PDF page ${page} for rejected suggestion`} onClose={() => setSourceOpen(false)} onClick={(event) => { if (event.target === event.currentTarget) sourceDrawerRef.current?.close(); }}>
          <section className="mvp-evidence-panel"><div className="mvp-evidence-heading"><div><span className="mvp-panel-kicker">SOURCE REVIEW</span><h2>PDF page {page}</h2></div><button type="button" className="mvp-icon-button" aria-label="Close source page" onClick={() => sourceDrawerRef.current?.close()}><X size={18} /></button></div>
            <PdfEvidenceViewer file={file} pageNumber={page} selectedBox={null} highlightLabel="Inspect this original page; no candidate highlight was verified" />
            <p className="mvp-review-note">No response-sheet row was created for the rejected suggestion. Review the page manually to decide whether it contains a requirement.</p>
          </section>
        </dialog>}
        <footer className="mvp-landing-footer"><span>Tender Review <span>·</span> Single-user pilot</span><span>Review the cited source before relying on any extracted requirement.</span></footer>
      </main>
    );
  }

  const reviewableRequirements = analysis.requirements.filter(item => item.rowType !== "section" && item.rowType !== "optional_heading");
  const checkedCount = reviewableRequirements.filter((item) => item.reviewed).length;
  const coveragePagesToShow = analysis.coverage?.pages.filter((item) => item.selectedForExtraction
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
  return (
    <main ref={motionRoot} className="tender-mvp-root mvp-review-screen">
      <header className="mvp-topbar mvp-review-topbar">
        <a className="mvp-brand" href="/" aria-label="Start a new tender"><span className="mvp-brand-mark"><TenderReviewMark /></span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Review workspace</small></span></a>
        <div className="mvp-topbar-right"><span className="mvp-file-name"><FileText size={15} />{analysis.filename}</span><span className="mvp-private"><span /> Single-user demo</span></div>
      </header>
      <section className="mvp-review-summarybar">
        <div className="mvp-review-title"><div className="mvp-eyebrow">TENDER REVIEW</div><h1>Technical requirements</h1><p>Review each extracted quote against its original page before you export.</p>{processing?.stage === "complete" && <p role="status">{processing.message}</p>}</div>
        <div className="mvp-review-stats" aria-label="Tender review summary">
          <div><span className="mvp-stat-icon"><FileCheck2 size={15} /></span><span><strong>{reviewableRequirements.length}</strong><small>Source requirements</small></span></div>
          {analysis.validationSummary && (
            <div><span className="mvp-stat-icon"><ShieldCheck size={15} /></span><span><strong>{analysis.validationSummary.verbatimPass + analysis.validationSummary.visualPass}<i> / {analysis.validationSummary.total}</i></strong><small>Tier 1/2 verified</small></span></div>
          )}
          {analysis.validationSummary && analysis.validationSummary.needsHumanReview > 0 && (
            <div><span className="mvp-stat-icon mvp-stat-icon-warn"><AlertTriangle size={15} /></span><span><strong>{analysis.validationSummary.needsHumanReview}</strong><small>Tier 3 human review</small></span></div>
          )}
          <div><span className="mvp-stat-icon mvp-stat-icon-warn"><Check size={15} /></span><span><strong>{checkedCount}<i> / {reviewableRequirements.length}</i></strong><small>Checked by you</small></span></div>
          <div><span className="mvp-stat-icon"><FileText size={15} /></span><span><strong>{analysis.pageCount}</strong><small>Tender pages</small></span></div>
        </div>
      </section>
      {responseSheet && <section className="mvp-sheet-panel" aria-label="Editable response sheet">
        <div className="mvp-sheet-heading">
          <div><span className="mvp-panel-kicker">EXPORT PREVIEW</span><h2>Response sheet <span>{responseSheet.rows.length} rows</span></h2><p>Edit the sheet before downloading. Click a citation to inspect the original page and highlighted source. Sheet edits apply to all downloads.</p></div>
          <div className="mvp-sheet-heading-actions">{sheetEdited && <button type="button" className="mvp-text-button mvp-sheet-reset" onClick={resetResponseSheet}>Reset sheet edits</button>}<button type="button" className="mvp-text-button mvp-sheet-reset" onClick={() => { setAnalysis(null); setResponseSheet(null); setSheetEdited(false); setFile(null); setError(null); setProcessing(null); setSourceOpen(false); }}>New tender</button></div>
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
                    {locked
                      ? <div className="mvp-sheet-citations">{(row.sourceRequirementIds?.length ? row.sourceRequirementIds : [row.sourceRequirementId]).map((sourceId, citationIndex) => {
                          const item = analysis.requirements.find(requirement => requirement.id === sourceId);
                          return item ? <button type="button" className={`mvp-sheet-source-link ${item.reviewed ? "is-checked" : ""} ${item.needsHumanReview || item.ocrWarning || item.precision === "page-only" || item.unverifiedVisualCompletion ? "is-ocr-warning" : ""}`} key={sourceId} aria-label={`View source for response row ${rowIndex + 1}, page ${item.page}, citation ${citationIndex + 1}`} title={item.unverifiedVisualCompletion ? "Unverified model visual-completion suggestion is not included in the response row" : item.needsHumanReview ? "Tier 3: Unverified quote — marked for human review" : item.ocrWarning ? "Tier 2: OCR source — verify transcription" : item.precision === "page-only" ? "Text verified on page; exact highlight unavailable" : item.reviewed ? "Source checked" : "Tier 1: Verbatim verified source"} onClick={() => openRequirement(item)}><FileText size={12} />p. {item.page}{row.sourceRequirementIds.length > 1 && <small>· {citationIndex + 1}</small>}{item.reviewed && <Check size={12} />}{item.unverifiedVisualCompletion ? <span>CHECK IMAGE</span> : item.needsHumanReview ? <span>REVIEW</span> : item.ocrWarning ? <span>OCR</span> : item.precision === "page-only" ? <span>PAGE</span> : null}</button> : null;
                        })}</div>
                      : <textarea
                        aria-label={`${column.header}, row ${rowIndex + 1}${rowSpan > 1 ? `, shared across ${rowSpan} rows` : ""}`}
                        rows={Math.min(4, Math.max(1, Math.ceil(value.length / (column.role === "requirement" ? 58 : 34))))}
                        value={value}
                        onChange={(event) => updateSheetCell(row.id, section.columnIndices[columnIndex], event.target.value)}
                      />}
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
              <small>{countLabel(analysis.coverage.summary.selectedTechnicalPages, "routed page")} · {countLabel(analysis.coverage.summary.sourceMatchedRequirements, "source matched requirement row")} · {countLabel(analysis.coverage.summary.rejectedSuggestions, "rejected suggestion")}</small>
            </summary>
            <p className="mvp-coverage-caveat">Counts describe what the parser, router, and page audit actually processed. A model audit reporting no gaps does not prove that the tender is complete.</p>
            <dl className="mvp-coverage-summary">
              <div><dt>Router input</dt><dd>{analysis.coverage.summary.routingPages} of {analysis.coverage.summary.documentPages} pages with native or OCR text</dd></div>
              <div><dt>Source table rows</dt><dd>{countLabel(analysis.coverage.summary.tableRowsDetected, "row")} detected · {countLabel(analysis.coverage.summary.tableRowsMappedToCandidates, "row")} mapped · {countLabel(analysis.coverage.summary.tableRowsExcludedAsHeaders, "header")} · {countLabel(analysis.coverage.summary.tableRowsEmpty, "empty row")} · {countLabel(analysis.coverage.summary.tableRowsUnmapped, "nonempty row")} unmapped, across {countLabel(analysis.coverage.summary.tablePagesWithKnownRowCount, "page")} with detected row geometry</dd></div>
              <div><dt>Suggestions and review</dt><dd>{countLabel(analysis.coverage.summary.candidateSuggestions, "model suggestion")} · {countLabel(analysis.coverage.summary.sourceMatchedRows, "source matched row")} including headings · {countLabel(analysis.coverage.summary.sourceMatchedRequirements, "source matched requirement row")} · {countLabel(currentNeedsReviewCount, "row")} awaiting your review</dd></div>
              <div><dt>Page audits</dt><dd>{analysis.coverage.summary.auditPagesWithNoGapsReported} reported no gaps · {analysis.coverage.summary.auditPagesWithPossibleGaps} flagged possible gaps · {analysis.coverage.summary.auditPagesIncomplete} incomplete · {analysis.coverage.summary.auditPagesNotRun} not run</dd></div>
              {analysis.coverage.summary.pagesWithoutSelectableText > 0 && <div><dt>OCR review</dt><dd>{countLabel(analysis.coverage.summary.pagesWithoutSelectableText, "page")} had no selectable text</dd></div>}
              {analysis.coverage.summary.pagesProcessedWithOcr > 0 && <div><dt>Local OCR</dt><dd>{countLabel(analysis.coverage.summary.pagesProcessedWithOcr, "page")} transcribed locally; verify every OCR-grounded row against the page image</dd></div>}
              {analysis.coverage.summary.clippedRoutingPages > 0 && <div><dt>Clipped router context</dt><dd>{countLabel(analysis.coverage.summary.clippedRoutingPages, "page")} had source text outside the routing excerpt</dd></div>}
              {analysis.coverage.summary.possibleOmissionSuggestions > 0 && <div><dt>Possible omissions</dt><dd>{countLabel(analysis.coverage.summary.possibleOmissionSuggestions, "source suggestion")} returned by the page audit; inspect the flagged pages</dd></div>}
              {analysis.coverage.summary.unattributedCandidateSuggestions > 0 && <div><dt>Unattributed suggestions</dt><dd>{countLabel(analysis.coverage.summary.unattributedCandidateSuggestions, "suggestion")} had no usable source page</dd></div>}
            </dl>
            <ul className="mvp-coverage-pages">
              {coveragePagesToShow.map((item) => {
                const rejectedOnPage = (analysis.rejectedSuggestionDetails ?? []).filter((suggestion) => suggestion.page === item.page);
                return <li key={item.page}>
                  <div className="mvp-coverage-page-title"><strong>PDF page {item.page}</strong><button type="button" onClick={() => { setCoverageFocus(null); setPage(item.page); setSourceOpen(true); }}>Open source page</button></div>
                  <span>{item.selectedForExtraction ? "Selected for extraction" : item.ocrPerformed ? "Local OCR completed · verify transcription" : item.ocrNeeded ? "Sparse text or image-backed page · OCR unavailable or unreadable" : "Considered by router, not selected"}</span>
                  {item.ocrNeeded && <span className="is-warning">OCR was needed but produced no transcript; inspect this source page manually.</span>}
                  {item.sourceTableRowsDetected !== null && <span>{countLabel(item.sourceTableRowsDetected, "source table row")} detected</span>}
                  {item.sourceTableRowsMappedToCandidates !== null && <span>{countLabel(item.sourceTableRowsMappedToCandidates, "row")} mapped to candidates · {countLabel(item.sourceTableRowsExcludedAsHeaders ?? 0, "header")} · {countLabel(item.sourceTableRowsEmpty ?? 0, "empty row")} · {countLabel(item.sourceTableRowsUnmapped ?? 0, "nonempty row")} unmapped</span>}
                  {Boolean(item.sourceTableCoverageRows?.length) && <div className="mvp-coverage-row-findings">
                    <strong>Detected source rows and their extraction coverage</strong>
                    {item.sourceTableCoverageRows?.map((row) => {
                      const status = row.disposition === "header" ? "repeated header"
                        : row.disposition === "empty" ? "empty row"
                          : row.disposition === "unmapped" ? "no candidate generated"
                          : `${countLabel(row.candidateSuggestions, "candidate")} · ${countLabel(row.sourceMatchedCandidates, "source-matched candidate")}`;
                      const needsInspection = row.disposition === "unmapped" || row.sourceMatchedCandidates < row.candidateSuggestions;
                      return <div className="mvp-coverage-row-finding" key={`${item.page}-${row.rowNumber}`}>
                        <span className={needsInspection ? "is-warning" : ""}><b>Detected row {row.rowNumber}</b> · {status}{row.textTruncated ? " · excerpt shortened" : ""}</span>
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
        <section className="mvp-evidence-panel" aria-label="Cited tender source">
          <div className="mvp-evidence-heading"><div><span className="mvp-panel-kicker">SOURCE EVIDENCE</span><h2 id="source-drawer-title">{coverageFocus?.page === page ? `Page ${page} source row` : active && active.page === page ? `Page ${page} citation` : `Page ${page} source`}</h2></div><div className="mvp-evidence-actions"><button className="mvp-icon-button" onClick={() => { setCoverageFocus(null); setPage((current) => Math.max(1, current - 1)); }} aria-label="Previous page" disabled={page <= 1}><ArrowLeft size={16} /></button><span><strong>{String(page).padStart(2, "0")}</strong> / {analysis.pageCount}</span><button className="mvp-icon-button" onClick={() => { setCoverageFocus(null); setPage((current) => Math.min(analysis.pageCount, current + 1)); }} aria-label="Next page" disabled={page >= analysis.pageCount}><ArrowRight size={16} /></button><button type="button" className="mvp-icon-button" aria-label="Close source drawer" onClick={() => sourceDrawerRef.current?.close()} autoFocus><X size={18} /></button></div></div>
          {sourceOpen && file && <PdfEvidenceViewer file={file} pageNumber={page} selectedBox={coverageFocus?.page === page ? coverageFocus.row.bbox : active?.page === page ? active.bbox : null} highlightLabel={coverageFocus?.page === page ? "Detected source row not matched to an extraction candidate; inspect its meaning" : active?.ocrWarning ? "Approximate table-row box for visually transcribed text; verify the full row" : "Bounding box for cited source quote"} />}
          <div className="mvp-citation-detail">
            <div className={`mvp-citation-label ${coverageFocus?.page === page ? "" : active?.needsHumanReview || active?.ocrWarning || active?.precision === "page-only" ? "is-ocr-warning" : ""}`}><span className="mvp-exact-dot" /> {coverageFocus?.page === page ? coverageRowReviewLabel(coverageFocus.row) : active?.needsHumanReview ? "UNVERIFIED CITATION · REQUIRES HUMAN REVIEW" : active?.ocrWarning ? "VISUAL TRANSCRIPTION · VERIFY IN SOURCE" : active?.precision === "page-only" ? "TEXT VERIFIED · LOCATION UNCERTAIN" : active?.parameter ? "SOURCE TABLE / LIST TEXT" : "EXACT SOURCE QUOTE"} <span>·</span> PAGE {String(coverageFocus?.page === page ? coverageFocus.page : active?.page ?? page).padStart(2, "0")}</div>
            <blockquote>{coverageFocus?.page === page ? coverageFocus.row.cells.filter(Boolean).join(" | ") : active?.quote ?? "Choose a requirement to inspect its tender source."}</blockquote>
            {coverageFocus?.page !== page && active?.selectableTextQuote && <div className="mvp-selectable-excerpt"><span>SELECTABLE PDF TEXT</span><p>{active.selectableTextQuote}</p></div>}
            {coverageFocus?.page !== page && active?.unverifiedVisualCompletion && <div className="mvp-selectable-excerpt"><span>UNVERIFIED VISUAL COMPLETION · NOT EXPORTED</span><p>{active.unverifiedVisualCompletion}</p><p>Model-proposed wording; compare it with the page image before using it.</p></div>}
            <div className="mvp-review-actions"><span>{coverageFocus?.page === page ? coverageRowReviewMessage(coverageFocus.row) : active?.reviewed ? "You checked this citation against the page." : page === active?.page && active?.needsHumanReview ? "This quote could not be verified automatically; inspect and verify manually against the page." : page === active?.page && active?.precision === "page-only" ? "The quote appears in this page text, but no exact highlight is available. Verify it manually." : page === active?.page && active?.bbox ? "Confirm the wording and highlight against the original." : "Open the cited page to check the quote and highlight."}</span><button disabled={Boolean(coverageFocus?.page === page) || !active || page !== active.page || (!active.bbox && active.precision === "exact")} className={active?.reviewed ? "mvp-check-button is-checked" : "mvp-check-button"} onClick={markReviewed}>{coverageFocus?.page === page ? "Source row" : active?.reviewed ? <><Check size={14} /> Checked</> : "Mark checked"}</button></div>
          </div>
        </section>
      </dialog>
    </main>
  );
}
