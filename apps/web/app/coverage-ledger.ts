export type CoverageAuditStatus = "not_run" | "incomplete" | "no_gaps_reported" | "possible_gaps_reported";
export type ExtractionStatus = "not_selected" | "complete" | "incomplete";

export type RejectedSuggestion = {
  page: number | null;
  reason: string;
  quotePreview: string;
};

export type CoverageSourceRow = {
  /** One-based position in the detected source table row sequence. */
  rowNumber: number;
  cells: string[];
  textTruncated: boolean;
  disposition: "candidate" | "header" | "empty" | "unmapped";
  candidateSuggestions: number;
  sourceMatchedCandidates: number;
  /** Percentages of the rendered page, matching the evidence viewer contract. */
  bbox: { x: number; y: number; width: number; height: number } | null;
};

export type PageCoverageRecord = {
  page: number;
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
  ocrNeeded: boolean;
};

export function collectSourceTableCoverageRows(
  rows: Array<{
    cells: string[];
    cellBoxes: Array<{ x: number; y: number; width: number; height: number } | null>;
    bbox: { x: number; y: number; width: number; height: number };
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
    return [{
      rowNumber: rowIndex + 1,
      cells: normalizedCells,
      textTruncated: cells.some((cell) => cell.length > 240),
      disposition,
      candidateSuggestions,
      sourceMatchedCandidates: 0,
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

export type CoverageReport = {
  pages: PageCoverageRecord[];
  summary: {
    documentPages: number;
    routingPages: number;
    selectedTechnicalPages: number;
    pagesWithoutSelectableText: number;
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
      pagesWithoutSelectableText: count((page) => !page.selectableTextAvailable),
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
