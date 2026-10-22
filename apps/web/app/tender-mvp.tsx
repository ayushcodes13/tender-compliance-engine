"use client";

import { useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, Check, FileCheck2, FileText, LoaderCircle, ScanSearch, ShieldCheck, Upload, X } from "lucide-react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { PdfEvidenceViewer } from "@/components/mvp/pdf-evidence-viewer";
import { analyzeTender } from "./actions";
import { prepareVisualComplianceRows } from "./visual-table";
import { complianceRowHeightTwips, reflowComplianceText, splitHeadingPrefix, verticalMergeAt } from "./compliance-format";

gsap.registerPlugin(useGSAP, ScrollTrigger);

type BoundingBox = { x: number; y: number; width: number; height: number };
type Requirement = {
  id: string;
  text: string;
  parameter?: string;
  specifications?: string[];
  sourceCells?: string[];
  remark?: string;
  rowType?: "section" | "requirement" | "optional_heading";
  headingPrefix?: string;
  mergeWithNext?: boolean;
  continuationOfPrevious?: boolean;
  sourceRowHeight?: number;
  sourceTextHeight?: number;
  exportGroupId?: string;
  category: string;
  page: number;
  quote: string;
  selectableTextQuote?: string;
  bbox: BoundingBox | null;
  precision: "exact" | "visual-ocr" | "page-only";
  ocrWarning?: boolean;
  reviewed: boolean;
};
type Analysis = {
  filename: string;
  pageCount: number;
  textPages: number;
  sectionTitle?: string;
  sectionHeading?: string;
  sourceColumns?: Array<{ header: string; role: "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other" }>;
  sheetTitle?: string;
  sheetHeading?: string;
  sheetProductTitle?: string;
  requirements: Requirement[];
  rejectedCandidates: number;
  extractionMode?: "rule-based-preview" | "structured-table" | "visual-compliance-sheet";
  reviewNote: string;
};

function splitRequirementSubpoints(text: string): string[] {
  return text
    .split(/(?=[\uF0B7\u2022\u25CF\u25AA]\s*|(?<=\s)o\s+(?!C\b)(?=[A-Z0-9])|(?<=\s)[1-9]\.\s+(?=[A-Z]))/)
    .map((part) => part.trim())
    .filter(Boolean);
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
  const [activeId, setActiveId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [showSourceDetail, setShowSourceDetail] = useState(false);

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
        gsap.fromTo(".mvp-review-topbar, .mvp-review-summarybar, .mvp-workspace", { autoAlpha: 0, y: 10 }, {
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
      type ExportColumn = { header: string; role: "heading" | "requirement" | "source" | "response" | "page"; sourceIndex?: number };
      const hasHeadingColumn = sourceColumns.some((column) => column.role === "heading");
      const exportColumns: ExportColumn[] = sourceColumns.flatMap((column, index): ExportColumn[] => {
        if (column.role === "heading") return [{ header: column.header || "Heading", role: "heading", sourceIndex: index }];
        if (column.role === "specification") return hasHeadingColumn
          ? [{ header: column.header || "Tender requirement", role: "requirement", sourceIndex: index }]
          : [{ header: "Heading", role: "heading" }, { header: column.header || "Tender requirement", role: "requirement", sourceIndex: index }];
        return [{ header: column.header || `Source column ${index + 1}`, role: "source", sourceIndex: index }];
      });
      const existingResponseField = sourceColumns.some((column) => ["compliance", "deviation", "remark"].includes(column.role));
      if (!existingResponseField) exportColumns.push({ header: "OEM response", role: "response" });
      exportColumns.push({ header: "Source page", role: "page" as const });
      const responseRows: Array<{ values: string[]; section?: boolean }> = [];
      const addResponseRow = (item: Requirement, heading: string, requirement: string) => {
        const values = exportColumns.map((column) => {
          if (column.role === "heading") return column.sourceIndex === undefined ? heading : item.sourceCells?.[column.sourceIndex] || heading;
          if (column.role === "requirement") return requirement;
          if (column.role === "response") return "";
          if (column.role === "page") return `Page ${item.page}`;
          return column.sourceIndex === undefined ? "" : item.sourceCells?.[column.sourceIndex] ?? "";
        });
        responseRows.push({ values });
      };
      const addSectionRow = (item: Requirement, heading: string, section: string) => {
        const values = exportColumns.map((column) => {
          if (column.role === "heading") return column.sourceIndex === undefined ? heading : item.sourceCells?.[column.sourceIndex] || heading;
          if (column.role === "requirement") return section;
          if (column.role === "page") return `Page ${item.page}`;
          return column.sourceIndex === undefined ? "" : item.sourceCells?.[column.sourceIndex] ?? "";
        });
        responseRows.push({ values, section: true });
      };
      let activeHeading = analysis.sheetProductTitle || analysis.sectionTitle || "";
      const structuralLabel = /^(?:section|part|chapter|annex(?:ure)?|schedule)\s*(?:[-:.)]?\s*)?(?:[ivxlcdm]+|\d+|[a-z])\s*[.:)-]?$/i;
      if (structured) {
        for (const item of analysis.requirements) {
          const heading = item.parameter ?? item.text;
          for (const specification of item.specifications?.length ? item.specifications : [item.quote]) {
            for (const subpoint of splitRequirementSubpoints(specification)) {
              addResponseRow(item, heading, subpoint.replace(/^\s*[•●]\s*/, ""));
            }
          }
        }
      } else {
        let productHeading = "";
        for (const item of analysis.requirements) {
          const label = item.text.trim();
          if (structuralLabel.test(label)) continue;
          if (item.rowType === "optional_heading") {
            if (productHeading) addSectionRow(item, productHeading, label);
            else {
              activeHeading = label;
              addSectionRow(item, label, "");
            }
            continue;
          }
          if (item.rowType === "section") {
            if (productHeading) addSectionRow(item, productHeading, label);
            else if (!/^\d+(?:\.\d+)*\s/.test(label)) {
              productHeading = label;
              activeHeading = label;
              addSectionRow(item, label, "");
            } else {
              activeHeading = label;
              addSectionRow(item, label, "");
            }
            continue;
          }
          const split = splitHeadingPrefix(label, item.headingPrefix);
          const requirement = split?.remainder.trim() || label;
          if (split?.heading.trim()) {
            productHeading ||= split.heading.trim();
            activeHeading = productHeading;
          }
          const heading = productHeading || activeHeading || analysis.sheetHeading || "Tender requirement";
          for (const subpoint of splitRequirementSubpoints(requirement)) {
            addResponseRow(item, heading, subpoint);
          }
        }
      }
      const headingColumnIndex = exportColumns.findIndex((column) => column.role === "heading");
      const headingValues = responseRows.map((row) => headingColumnIndex < 0 ? "" : row.values[headingColumnIndex] ?? "");
      const rows = [
        new TableRow({ tableHeader: true, children: exportColumns.map((column) => cell(column.header, true, AlignmentType.CENTER)) }),
        ...responseRows.map((item, rowIndex) => new TableRow({
          cantSplit: true,
          children: item.values.map((value, columnIndex) => {
            const merge = columnIndex === headingColumnIndex
              ? verticalMergeAt(headingValues, rowIndex)
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
          new Paragraph({ text: `${analysis.requirements.length} source-matched requirements · ${analysis.requirements.filter((item) => item.reviewed).length} checked by reviewer` }),
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
          <p>It processes text-based PDFs in this browser session. Scanned PDFs need OCR, which is not included. The extracted rows are a review starting point, not a guarantee that every tender requirement was found. Always check the tender source before relying on the response sheet.</p>
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
          <div className="mvp-upload-intro"><div className="mvp-eyebrow"><span className="mvp-eyebrow-mark" /> STEP 1 OF 3</div><h1>Start with the tender document.</h1><p>Choose a text-based PDF. Tender Review will find requirement quotes, check them against the cited page, and show you the matching source.</p><ul><li>PDF only · maximum 4 MB</li><li>Up to 120 pages</li><li>Scanned PDFs are not supported yet</li></ul></div>
          <div className="mvp-upload-card">
            <div className="mvp-upload-card-heading"><span className="mvp-upload-step">SELECT YOUR TENDER</span><span className="mvp-upload-private"><span /> Single browser session</span></div>
            <form onSubmit={analyze}>
              <label className={`mvp-dropzone ${file ? "is-ready" : ""}`} htmlFor="tender-file">
                <input id="tender-file" type="file" accept="application/pdf,.pdf" onChange={selectFile} />
                <span className="mvp-upload-icon"><Upload size={20} /></span>
                {file ? <><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · ready to review</span></> : <><strong>Choose a tender PDF</strong><span>PDF files up to 4 MB</span></>}
                <span className="mvp-browse-link">Select PDF <ArrowUpRight size={14} /></span>
              </label>
              <button className="mvp-primary mvp-submit" type="submit" disabled={!file || busy}>
                {busy ? <><LoaderCircle className="mvp-spin" size={17} /> Reading the PDF…</> : <>Find requirements <ArrowRight size={17} /></>}
              </button>
              {error && <p className="mvp-error" role="alert">{error}</p>}
            </form>
            <div className="mvp-upload-limits"><span><FileCheck2 size={15} /> Review every quote</span><span><ShieldCheck size={15} /> Nothing marked checked for you</span></div>
          </div>
        </section>
        <footer className="mvp-landing-footer"><span>Tender Review <span>·</span> Single-user pilot</span><span>Review the cited source before relying on any extracted requirement.</span></footer>
      </main>
    );
  }

  const checkedCount = analysis.requirements.filter((item) => item.reviewed).length;
  return (
    <main ref={motionRoot} className="tender-mvp-root mvp-review-screen">
      <header className="mvp-topbar mvp-review-topbar">
        <a className="mvp-brand" href="/" aria-label="Start a new tender"><span className="mvp-brand-mark"><TenderReviewMark /></span><span className="mvp-brand-copy"><strong>Tender Review</strong><small>Review workspace</small></span></a>
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
          <p className="mvp-review-note">{analysis.reviewNote}{analysis.extractionMode === "structured-table" ? "" : ` ${analysis.rejectedCandidates ? `${analysis.rejectedCandidates} unmatched model suggestions were left out.` : "Unmatched suggestions are left out."}`}</p>
          <div className="mvp-requirement-list">
            {analysis.requirements.map((item, index) => (
              <button className={`mvp-requirement ${active?.id === item.id ? "is-active" : ""}`} key={item.id} onClick={() => openRequirement(item)}>
                <span className="mvp-req-topline"><span>REQ {String(index + 1).padStart(3, "0")}</span><span className={`mvp-citation-tag ${item.ocrWarning ? "is-ocr-warning" : ""}`}>Page {item.page} · {item.ocrWarning ? "OCR warning" : item.precision === "page-only" ? "page only" : "exact"}</span></span>
                <span className={`mvp-req-text ${item.parameter ? "mvp-req-structured" : ""}`}>
                  {item.parameter ? <><strong className="mvp-req-parameter">{item.parameter}</strong>{item.specifications?.map((specification, specIndex) => <span className={`mvp-req-spec ${item.quote.startsWith("•") ? "is-bullet" : ""}`} key={`${item.id}-spec-${specIndex}`}>{specification}</span>)}</> : item.text}
                </span>
                <span className="mvp-req-bottom"><span>{item.category}</span><span className={item.reviewed ? "mvp-reviewed" : "mvp-unreviewed"}>{item.reviewed ? "Checked" : "Needs review"}</span></span>
              </button>
            ))}
          </div>
        <div className="mvp-list-footer"><button className="mvp-export" onClick={exportDocx} disabled={exporting || analysis.requirements.length === 0}>{exporting ? <LoaderCircle className="mvp-spin" size={16} /> : <ArrowDownToLine size={16} />}{exporting ? "Building DOCX…" : "Download response sheet"}</button><p>{analysis.extractionMode === "structured-table" ? "DOCX preserves each parameter and leaves compliance and remarks blank." : analysis.extractionMode === "visual-compliance-sheet" ? "DOCX follows the source compliance sheet with blank compliance cells; verify each cited row." : "DOCX includes source pages and blank OEM response cells."}</p>{error && <p className="mvp-error" role="alert">{error}</p>}</div>
        </section>

        <section className="mvp-evidence-panel" aria-label="Cited tender source">
          <div className="mvp-evidence-heading"><div><span className="mvp-panel-kicker">SOURCE EVIDENCE</span><h2>{active && active.page === page ? `Page ${page} citation` : `Page ${page} source`}</h2></div><div className="mvp-evidence-actions"><button className="mvp-icon-button" onClick={() => setPage((current) => Math.max(1, current - 1))} aria-label="Previous page" disabled={page <= 1}><ArrowLeft size={16} /></button><span><strong>{String(page).padStart(2, "0")}</strong> / {analysis.pageCount}</span><button className="mvp-icon-button" onClick={() => setPage((current) => Math.min(analysis.pageCount, current + 1))} aria-label="Next page" disabled={page >= analysis.pageCount}><ArrowRight size={16} /></button></div></div>
          {file && <PdfEvidenceViewer file={file} pageNumber={page} selectedBox={active?.page === page ? active.bbox : null} highlightLabel={active?.ocrWarning ? "Approximate table-row box for visually transcribed text; verify the full row" : "Bounding box for cited source quote"} />}
          <div className="mvp-citation-detail">
            <div className={`mvp-citation-label ${active?.ocrWarning ? "is-ocr-warning" : ""}`}><span className="mvp-exact-dot" /> {active?.ocrWarning ? "VISUAL TRANSCRIPTION · VERIFY IN SOURCE" : active?.parameter ? "SOURCE TABLE / LIST TEXT" : "EXACT SOURCE QUOTE"} <span>·</span> PAGE {String(active?.page ?? page).padStart(2, "0")}</div>
            <blockquote>{active?.quote ?? "Choose a requirement to inspect its tender source."}</blockquote>
            {active?.selectableTextQuote && <div className="mvp-selectable-excerpt"><span>SELECTABLE PDF TEXT</span><p>{active.selectableTextQuote}</p></div>}
            <div className="mvp-review-actions"><span>{active?.reviewed ? "You checked this citation against the page." : page === active?.page && active?.bbox ? "Confirm the wording and highlight against the original." : "Open the cited page to check the quote and highlight."}</span><button disabled={!active || page !== active.page || !active.bbox} className={active?.reviewed ? "mvp-check-button is-checked" : "mvp-check-button"} onClick={markReviewed}>{active?.reviewed ? <><Check size={14} /> Checked</> : "Mark checked"}</button></div>
          </div>
        </section>
      </div>
    </main>
  );
}
