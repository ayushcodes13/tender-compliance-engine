import type { SourceBox, SourcePageOcrSkipReason, SourcePageOcrStatus } from "./source-document.ts";

export type CoverageAuditStatus = "not_run" | "incomplete" | "no_gaps_reported" | "possible_gaps_reported";
export type ExtractionStatus = "not_selected" | "complete" | "incomplete";
export type RoutingDisposition = "selected" | "uncertain" | "unrouted" | "no_text";

export function resolveRoutingDisposition(input: {
  hasRoutingText: boolean;
  selectedForExtraction: boolean;
  selectedByAnnexureContinuation: boolean;
  markedUncertain: boolean;
  matchingSections: Array<{ title: string; reason: string }>;
}): { disposition: RoutingDisposition; reason: string } {
  if (!input.hasRoutingText) {
    return { disposition: "no_text", reason: "No native or OCR text was available to the router; inspect the page image." };
  }
  if (input.selectedForExtraction) {
    const sectionContext = input.matchingSections.length
      ? input.matchingSections.map((section) => `${section.title.slice(0, 120)}: ${section.reason.slice(0, 280)}`).join("; ").slice(0, 800)
      : input.selectedByAnnexureContinuation
        ? "Retained as a page in a parser-detected annexure continuation."
        : "Selected by the router; no matching section reason was retained.";
    return {
      disposition: "selected",
      reason: input.markedUncertain ? `${sectionContext} The router also marked this page uncertain.` : sectionContext,
    };
  }
  if (input.markedUncertain) {
    return { disposition: "uncertain", reason: "The router marked this page uncertain; it was not included in extraction and needs source review." };
  }
  return {
    disposition: "unrouted",
    reason: "No section range or uncertainty disposition was returned for this page; do not treat it as confirmed irrelevant.",
  };
}

export type RejectedSuggestion = {
  page: number | null;
  reason: string;
  quotePreview: string;
};

export type SourceRowClassification = "requirement" | "section" | "optional_heading" | "header" | "instruction" | "ambiguous" | "unclassified";
export type SourceRowClassificationReason = "technical_obligation" | "structural_heading" | "optional_item_heading" | "header_or_page_furniture" | "process_or_submission_instruction" | "commercial_or_eligibility_term" | "ambiguous_source_structure" | "classification_unavailable";

const CLASSIFICATION_REASONS: Record<Exclude<SourceRowClassification, "unclassified">, SourceRowClassificationReason[]> = {
  requirement: ["technical_obligation"],
  section: ["structural_heading"],
  optional_heading: ["optional_item_heading"],
  header: ["header_or_page_furniture"],
  instruction: ["process_or_submission_instruction", "commercial_or_eligibility_term"],
  ambiguous: ["ambiguous_source_structure"],
};

export function resolveSourceRowClassification(input: { rowType?: string; reason?: string }): {
  rowType: SourceRowClassification;
  reason: SourceRowClassificationReason;
  valid: boolean;
} {
  if (input.rowType && input.reason && Object.hasOwn(CLASSIFICATION_REASONS, input.rowType)
    && CLASSIFICATION_REASONS[input.rowType as Exclude<SourceRowClassification, "unclassified">].includes(input.reason as SourceRowClassificationReason)) {
    return { rowType: input.rowType as SourceRowClassification, reason: input.reason as SourceRowClassificationReason, valid: true };
  }
  return { rowType: "ambiguous", reason: "ambiguous_source_structure", valid: false };
}

export function describeRejectedSuggestion(reason: string): string {
  if (reason === "source_quote_or_location_not_verified") {
    return "Not added to the response sheet: the wording could not be verified against source text or OCR evidence on this page. Inspect the source page before relying on it.";
  }
  if (reason === "page_not_selected_by_router") {
    return "Not added to the response sheet: its page was not selected for extraction.";
  }
  return `Not added to the response sheet: ${reason.replace(/_/g, " ")}.`;
}

export type CoverageSourceRow = {
  /** One-based position in the detected source table row sequence. */
  rowNumber: number;
  cells: string[];
  textTruncated: boolean;
  disposition: "candidate" | "header" | "empty" | "unmapped";
  candidateSuggestions: number;
  sourceMatchedCandidates: number;
  matchedRequirementIds: string[];
  acceptedLinkStatus: "not_applicable" | "no_candidate_suggestions" | "linked" | "unlinked";
  /** Source association does not establish that every obligation in the row was extracted. */
  semanticCoverageStatus: "not_applicable" | "not_assessed";
  sourceClassification: SourceRowClassification;
  classificationReason: SourceRowClassificationReason;
  sourceElementIds: string[];
  sourceTableId: string | null;
  sourceRowId: string | null;
  /** Percentages of the rendered page, matching the evidence viewer contract. */
  bbox: { x: number; y: number; width: number; height: number } | null;
};

export type PageCoverageRecord = {
  page: number;
  routingDisposition: RoutingDisposition;
  routingReason: string;
  routerMarkedUncertain: boolean;
  selectableTextAvailable: boolean;
  routingInputIncluded: boolean;
  routingContextClipped: boolean;
  selectedForExtraction: boolean;
  extractionStatus: ExtractionStatus;
  sourceTableRowsDetected: number | null;
  sourceTableRowsMappedToCandidates: number | null;
  sourceTableRowsExcludedAsHeaders: number | null;
  sourceTableRowsEmpty: number | null;
  sourceTableRowsUnmapped: number | null;
  sourceTableCoverageRows?: CoverageSourceRow[];
  sourceTableRowsNotShown?: number;
  candidateSuggestions: number;
  sourceMatchedRows: number;
  sourceMatchedRequirements: number;
  needsHumanReview: number;
  rejectedSuggestions: number;
  rejectionReasons: Array<{ reason: string; count: number }>;
  auditStatus: CoverageAuditStatus;
  possibleOmissionSuggestions: number;
  hasRasterImageContent: boolean;
  imageRegions: Array<{ id: string; bbox: SourceBox; areaRatio: number }>;
  ocrRecommended: boolean;
  ocrStatus: SourcePageOcrStatus;
  ocrSkipReason?: SourcePageOcrSkipReason;
  ocrNeeded: boolean;
  ocrPerformed: boolean;
};

export function collectSourceTableCoverageRows(
  rows: Array<{
    cells: string[];
    cellBoxes: Array<{ x: number; y: number; width: number; height: number } | null>;
    bbox: { x: number; y: number; width: number; height: number };
    sourceElementIds?: string[];
    sourceTableId?: string;
    sourceRowId?: string;
    sourceClassification?: SourceRowClassification;
    classificationReason?: SourceRowClassificationReason;
  }>,
  candidateCountByRow: Map<number, number>,
  excludedHeaderIndices: Set<number>,
  pageSize: { width: number; height: number },
  maxRows = 12,
): { rows: CoverageSourceRow[]; count: number; notShown: number } {
  const findings = rows.flatMap((row, rowIndex) => {
    const cells = row.cells.map((cell) => cell.trim());
    const populated = cells.some(Boolean);
    const isHeader = excludedHeaderIndices.has(rowIndex);
    const candidateSuggestions = candidateCountByRow.get(rowIndex) ?? 0;
    const disposition: CoverageSourceRow["disposition"] = isHeader ? "header"
      : !populated ? "empty"
        : candidateSuggestions > 0 ? "candidate" : "unmapped";

    const boxes = row.cellBoxes.filter((box): box is NonNullable<typeof box> => Boolean(box));
    const sourceBox = boxes.length ? {
      x: Math.min(...boxes.map((box) => box.x)),
      y: Math.min(...boxes.map((box) => box.y)),
      width: Math.max(...boxes.map((box) => box.x + box.width)) - Math.min(...boxes.map((box) => box.x)),
      height: Math.max(...boxes.map((box) => box.y + box.height)) - Math.min(...boxes.map((box) => box.y)),
    } : row.bbox;
    const normalizedCells = cells.map((cell) => cell.length > 240 ? `${cell.slice(0, 237)}…` : cell);
    const acceptedLinkStatus: CoverageSourceRow["acceptedLinkStatus"] = isHeader || !populated
      ? "not_applicable"
      : candidateSuggestions === 0 ? "no_candidate_suggestions" : "unlinked";
    const semanticCoverageStatus: CoverageSourceRow["semanticCoverageStatus"] = isHeader || !populated ? "not_applicable" : "not_assessed";
    return [{
      rowNumber: rowIndex + 1,
      cells: normalizedCells,
      textTruncated: cells.some((cell) => cell.length > 240),
      disposition,
      candidateSuggestions,
      sourceMatchedCandidates: 0,
      matchedRequirementIds: [],
      acceptedLinkStatus,
      semanticCoverageStatus,
      sourceElementIds: row.sourceElementIds ?? [],
      sourceTableId: row.sourceTableId ?? null,
      sourceRowId: row.sourceRowId ?? null,
      sourceClassification: row.sourceClassification ?? "unclassified",
      classificationReason: row.classificationReason ?? "classification_unavailable",
      bbox: pageSize.width > 0 && pageSize.height > 0 && sourceBox ? {
        x: sourceBox.x / pageSize.width * 100,
        y: sourceBox.y / pageSize.height * 100,
        width: sourceBox.width / pageSize.width * 100,
        height: sourceBox.height / pageSize.height * 100,
      } : null,
    }];
  });
  return {
    rows: findings.slice(0, Math.max(0, maxRows)),
    count: rows.filter((row, rowIndex) => row.cells.some((cell) => cell.trim())
      && !excludedHeaderIndices.has(rowIndex)
      && (candidateCountByRow.get(rowIndex) ?? 0) === 0).length,
    notShown: Math.max(0, findings.length - Math.max(0, maxRows)),
  };
}

/** Link table-row inventory entries to accepted requirements; semantic completeness remains unassessed. */
export function linkSourceRowsToRequirements(
  rows: CoverageSourceRow[],
  pageNumber: number,
  requirements: Array<{ id: string; page: number; sourceRowIndex?: number; sourceElementIds: string[] }>,
): CoverageSourceRow[] {
  return rows.map((row) => {
    // Table IDs are shared by every row; only row/cell IDs can identify a row-specific source.
    const sourceIds = new Set([
      ...(row.sourceRowId ? [row.sourceRowId] : []),
      ...row.sourceElementIds.filter((id) => id !== row.sourceTableId),
    ]);
    const linked = requirements.filter((requirement) => requirement.page === pageNumber
      && (requirement.sourceRowIndex === row.rowNumber - 1
        || requirement.sourceElementIds.some((id) => sourceIds.has(id))));
    const acceptedLinkStatus: CoverageSourceRow["acceptedLinkStatus"] = row.disposition === "header" || row.disposition === "empty"
      ? "not_applicable"
      : linked.length > 0
        ? "linked"
        : row.candidateSuggestions === 0 ? "no_candidate_suggestions" : "unlinked";
    return {
      ...row,
      sourceMatchedCandidates: linked.length,
      matchedRequirementIds: linked.map((requirement) => requirement.id),
      acceptedLinkStatus,
    };
  });
}

export type CoverageReport = {
  pages: PageCoverageRecord[];
  summary: {
    documentPages: number;
    routingPages: number;
    selectedTechnicalPages: number;
    routingPagesUncertain: number;
    routingPagesUnrouted: number;
    routingPagesWithoutText: number;
    pagesWithoutSelectableText: number;
    pagesWithRasterImageContent: number;
    ocrRecommendedPages: number;
    ocrAttemptedPages: number;
    ocrSkippedPages: number;
    ocrFailedPages: number;
    ocrCompletedWithoutTextPages: number;
    pagesProcessedWithOcr: number;
    clippedRoutingPages: number;
    tableRowsDetected: number;
    tablePagesWithKnownRowCount: number;
    tableRowsMappedToCandidates: number;
    tableRowsExcludedAsHeaders: number;
    tableRowsEmpty: number;
    tableRowsUnmapped: number;
    candidateSuggestions: number;
    sourceMatchedRows: number;
    sourceMatchedRequirements: number;
    needsHumanReview: number;
    rejectedSuggestions: number;
    unattributedCandidateSuggestions: number;
    unattributedRejectedSuggestions: number;
    auditPagesWithNoGapsReported: number;
    auditPagesWithPossibleGaps: number;
    auditPagesIncomplete: number;
    auditPagesNotRun: number;
    possibleOmissionSuggestions: number;
  };
};

export function buildCoverageReport(
  pages: PageCoverageRecord[],
  unattributed = { candidateSuggestions: 0, rejectedSuggestions: 0 },
): CoverageReport {
  const orderedPages = [...pages].sort((left, right) => left.page - right.page);
  const sum = (value: (page: PageCoverageRecord) => number) => orderedPages.reduce((total, page) => total + value(page), 0);
  const count = (predicate: (page: PageCoverageRecord) => boolean) => orderedPages.filter(predicate).length;

  return {
    pages: orderedPages,
    summary: {
      documentPages: orderedPages.length,
      routingPages: count((page) => page.routingInputIncluded),
      selectedTechnicalPages: count((page) => page.selectedForExtraction),
      routingPagesUncertain: count((page) => page.routingDisposition === "uncertain" || page.routerMarkedUncertain),
      routingPagesUnrouted: count((page) => page.routingDisposition === "unrouted"),
      routingPagesWithoutText: count((page) => page.routingDisposition === "no_text"),
      pagesWithoutSelectableText: count((page) => !page.selectableTextAvailable),
      pagesWithRasterImageContent: count((page) => page.hasRasterImageContent),
      ocrRecommendedPages: count((page) => page.ocrRecommended),
      ocrAttemptedPages: count((page) => ["text-found", "no-text-found", "failed"].includes(page.ocrStatus)),
      ocrSkippedPages: count((page) => page.ocrStatus === "not-attempted"),
      ocrFailedPages: count((page) => page.ocrStatus === "failed"),
      ocrCompletedWithoutTextPages: count((page) => page.ocrStatus === "no-text-found"),
      pagesProcessedWithOcr: count((page) => page.ocrPerformed),
      clippedRoutingPages: count((page) => page.routingContextClipped),
      tableRowsDetected: sum((page) => page.sourceTableRowsDetected ?? 0),
      tablePagesWithKnownRowCount: count((page) => page.sourceTableRowsDetected !== null),
      tableRowsMappedToCandidates: sum((page) => page.sourceTableRowsMappedToCandidates ?? 0),
      tableRowsExcludedAsHeaders: sum((page) => page.sourceTableRowsExcludedAsHeaders ?? 0),
      tableRowsEmpty: sum((page) => page.sourceTableRowsEmpty ?? 0),
      tableRowsUnmapped: sum((page) => page.sourceTableRowsUnmapped ?? 0),
      candidateSuggestions: sum((page) => page.candidateSuggestions),
      sourceMatchedRows: sum((page) => page.sourceMatchedRows),
      sourceMatchedRequirements: sum((page) => page.sourceMatchedRequirements),
      needsHumanReview: sum((page) => page.needsHumanReview),
      rejectedSuggestions: sum((page) => page.rejectedSuggestions) + unattributed.rejectedSuggestions,
      unattributedCandidateSuggestions: unattributed.candidateSuggestions,
      unattributedRejectedSuggestions: unattributed.rejectedSuggestions,
      auditPagesWithNoGapsReported: count((page) => page.auditStatus === "no_gaps_reported"),
      auditPagesWithPossibleGaps: count((page) => page.auditStatus === "possible_gaps_reported"),
      auditPagesIncomplete: count((page) => page.auditStatus === "incomplete"),
      auditPagesNotRun: count((page) => page.auditStatus === "not_run"),
      possibleOmissionSuggestions: sum((page) => page.possibleOmissionSuggestions),
    },
  };
}
