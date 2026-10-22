export type CoverageAuditStatus = "not_run" | "incomplete" | "no_gaps_reported" | "possible_gaps_reported";
export type ExtractionStatus = "not_selected" | "complete" | "incomplete";

export type RejectedSuggestion = {
  page: number | null;
  reason: string;
  quotePreview: string;
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
