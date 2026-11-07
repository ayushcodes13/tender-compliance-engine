import test from "node:test";
import assert from "node:assert/strict";
import { buildCoverageReport, collectSourceTableCoverageRows, describeRejectedSuggestion, linkSourceRowsToRequirements, resolveRoutingDisposition, resolveSourceRowClassification } from "./coverage-ledger.ts";

test("row classification reasons must agree with the structural class and mismatch stays ambiguous", () => {
  assert.deepEqual(resolveSourceRowClassification({ rowType: "instruction", reason: "commercial_or_eligibility_term" }), {
    rowType: "instruction", reason: "commercial_or_eligibility_term", valid: true,
  });
  assert.deepEqual(resolveSourceRowClassification({ rowType: "header", reason: "technical_obligation" }), {
    rowType: "ambiguous", reason: "ambiguous_source_structure", valid: false,
  });
  assert.deepEqual(resolveSourceRowClassification({ rowType: "ambiguous", reason: "ambiguous_source_structure" }), {
    rowType: "ambiguous", reason: "ambiguous_source_structure", valid: true,
  });
});

test("explains why unsupported candidate text is excluded and directs reviewers to the source", () => {
  assert.equal(
    describeRejectedSuggestion("source_quote_or_location_not_verified"),
    "Not added to the response sheet: the wording could not be verified against source text or OCR evidence on this page. Inspect the source page before relying on it.",
  );
  assert.equal(
    describeRejectedSuggestion("page_not_selected_by_router"),
    "Not added to the response sheet: its page was not selected for extraction.",
  );
});

const record = (page, overrides = {}) => ({
  page,
  routingDisposition: "selected",
  routingReason: "Selected by the test router.",
  routerMarkedUncertain: false,
  selectableTextAvailable: true,
  routingInputIncluded: true,
  routingContextClipped: false,
  selectedForExtraction: true,
  extractionStatus: "complete",
  sourceTableRowsDetected: null,
  sourceTableRowsMappedToCandidates: null,
  sourceTableRowsExcludedAsHeaders: null,
  sourceTableRowsEmpty: null,
  sourceTableRowsUnmapped: null,
  candidateSuggestions: 2,
  sourceMatchedRows: 1,
  sourceMatchedRequirements: 1,
  needsHumanReview: 1,
  rejectedSuggestions: 1,
  rejectionReasons: [{ reason: "source_quote_or_location_not_verified", count: 1 }],
  auditStatus: "not_run",
  possibleOmissionSuggestions: 0,
  hasRasterImageContent: false,
  imageRegions: [],
  ocrRecommended: false,
  ocrStatus: "not-recommended",
  ocrNeeded: false,
  ocrPerformed: false,
  ...overrides,
});

test("summarizes document and selected-page coverage without calling unrun audits complete", () => {
  const report = buildCoverageReport([
    record(3, { sourceTableRowsDetected: 14, sourceTableRowsMappedToCandidates: 9, sourceTableRowsExcludedAsHeaders: 2, sourceTableRowsEmpty: 1, sourceTableRowsUnmapped: 2, auditStatus: "no_gaps_reported" }),
    record(1, { selectableTextAvailable: false, routingInputIncluded: false, selectedForExtraction: false, extractionStatus: "not_selected", ocrNeeded: true, ocrPerformed: false, sourceTableRowsDetected: null, candidateSuggestions: 0, sourceMatchedRows: 0, sourceMatchedRequirements: 0, needsHumanReview: 0, rejectedSuggestions: 0, rejectionReasons: [], auditStatus: "not_run" }),
    record(2, { selectedForExtraction: false, extractionStatus: "not_selected", routingContextClipped: true, sourceTableRowsDetected: 0, sourceTableRowsMappedToCandidates: 0, sourceTableRowsExcludedAsHeaders: 0, sourceTableRowsEmpty: 0, sourceTableRowsUnmapped: 0, candidateSuggestions: 0, sourceMatchedRows: 0, sourceMatchedRequirements: 0, needsHumanReview: 0, rejectedSuggestions: 0, rejectionReasons: [], auditStatus: "incomplete" }),
  ]);

  assert.deepEqual(report.pages.map((page) => page.page), [1, 2, 3]);
  assert.equal(report.summary.documentPages, 3);
  assert.equal(report.summary.routingPages, 2);
  assert.equal(report.summary.selectedTechnicalPages, 1);
  assert.equal(report.summary.pagesWithoutSelectableText, 1);
  assert.equal(report.summary.pagesProcessedWithOcr, 0);
  assert.equal(report.summary.clippedRoutingPages, 1);
  assert.equal(report.summary.tableRowsDetected, 14);
  assert.equal(report.summary.tablePagesWithKnownRowCount, 2);
  assert.equal(report.summary.tableRowsMappedToCandidates, 9);
  assert.equal(report.summary.tableRowsExcludedAsHeaders, 2);
  assert.equal(report.summary.tableRowsEmpty, 1);
  assert.equal(report.summary.tableRowsUnmapped, 2);
  assert.equal(report.summary.sourceMatchedRows, 1);
  assert.equal(report.summary.auditPagesWithNoGapsReported, 1);
  assert.equal(report.summary.auditPagesIncomplete, 1);
  assert.equal(report.summary.auditPagesNotRun, 1);
});

test("distinguishes OCR processed pages from pages that still need OCR", () => {
  const report = buildCoverageReport([
    record(1, { selectableTextAvailable: false, ocrNeeded: true, ocrPerformed: true }),
    record(2, { selectableTextAvailable: false, ocrNeeded: true, ocrPerformed: false }),
  ]);
  assert.equal(report.summary.pagesWithoutSelectableText, 2);
  assert.equal(report.summary.pagesProcessedWithOcr, 1);
});

test("reports image content, OCR attempts, skipped runs, failures, and empty OCR separately", () => {
  const report = buildCoverageReport([
    record(1, { hasRasterImageContent: true, ocrRecommended: true, ocrStatus: "text-found", ocrPerformed: true }),
    record(2, { hasRasterImageContent: true, ocrRecommended: true, ocrStatus: "no-text-found", ocrNeeded: true }),
    record(3, { hasRasterImageContent: true, ocrRecommended: true, ocrStatus: "not-attempted", ocrSkipReason: "engine-unavailable", ocrNeeded: true }),
    record(4, { ocrRecommended: true, ocrStatus: "not-attempted", ocrSkipReason: "time-budget", ocrNeeded: true }),
    record(5, { ocrRecommended: true, ocrStatus: "failed", ocrNeeded: true }),
    record(6),
  ]);

  assert.equal(report.summary.pagesWithRasterImageContent, 3);
  assert.equal(report.summary.ocrRecommendedPages, 5);
  assert.equal(report.summary.ocrAttemptedPages, 3);
  assert.equal(report.summary.ocrSkippedPages, 2);
  assert.equal(report.summary.ocrFailedPages, 1);
  assert.equal(report.summary.ocrCompletedWithoutTextPages, 1);
  assert.equal(report.summary.pagesProcessedWithOcr, 1);
  assert.equal(report.pages[2].ocrSkipReason, "engine-unavailable");
});

test("keeps model-reported gaps and rejected suggestions visible in totals", () => {
  const report = buildCoverageReport([
    record(5, { auditStatus: "possible_gaps_reported", possibleOmissionSuggestions: 3, rejectedSuggestions: 2, rejectionReasons: [{ reason: "source_quote_or_location_not_verified", count: 2 }] }),
  ]);

  assert.equal(report.summary.auditPagesWithPossibleGaps, 1);
  assert.equal(report.summary.possibleOmissionSuggestions, 3);
  assert.equal(report.summary.rejectedSuggestions, 2);
});

test("preserves explicit incomplete and not-run states instead of inferring success", () => {
  const report = buildCoverageReport([
    record(1, { auditStatus: "incomplete" }),
    record(2, { auditStatus: "not_run" }),
  ]);
  assert.equal(report.summary.auditPagesIncomplete, 1);
  assert.equal(report.summary.auditPagesNotRun, 1);
  assert.equal(report.summary.auditPagesWithNoGapsReported, 0);
});

test("keeps uncertain, unrouted, and textless pages distinct from selected pages", () => {
  assert.deepEqual(resolveRoutingDisposition({
    hasRoutingText: true,
    selectedForExtraction: true,
    selectedByAnnexureContinuation: false,
    markedUncertain: true,
    matchingSections: [{ title: "Technical specifications", reason: "Contains equipment limits" }],
  }), {
    disposition: "selected",
    reason: "Technical specifications: Contains equipment limits The router also marked this page uncertain.",
  });
  assert.deepEqual(resolveRoutingDisposition({
    hasRoutingText: true,
    selectedForExtraction: false,
    selectedByAnnexureContinuation: false,
    markedUncertain: true,
    matchingSections: [],
  }), {
    disposition: "uncertain",
    reason: "The router marked this page uncertain; it was not included in extraction and needs source review.",
  });
  assert.deepEqual(resolveRoutingDisposition({
    hasRoutingText: true,
    selectedForExtraction: false,
    selectedByAnnexureContinuation: false,
    markedUncertain: false,
    matchingSections: [],
  }), {
    disposition: "unrouted",
    reason: "No section range or uncertainty disposition was returned for this page; do not treat it as confirmed irrelevant.",
  });
  assert.equal(resolveRoutingDisposition({
    hasRoutingText: false,
    selectedForExtraction: false,
    selectedByAnnexureContinuation: false,
    markedUncertain: false,
    matchingSections: [],
  }).disposition, "no_text");
  assert.equal(resolveRoutingDisposition({
    hasRoutingText: true,
    selectedForExtraction: true,
    selectedByAnnexureContinuation: true,
    markedUncertain: false,
    matchingSections: [],
  }).reason, "Retained as a page in a parser-detected annexure continuation.");
});

test("reports per-page router dispositions in document totals", () => {
  const report = buildCoverageReport([
    record(1),
    record(2, { routingDisposition: "uncertain", selectedForExtraction: false }),
    record(3, { routingDisposition: "unrouted", selectedForExtraction: false }),
    record(4, { routingDisposition: "no_text", selectableTextAvailable: false, routingInputIncluded: false, selectedForExtraction: false }),
    record(5, { routingDisposition: "selected", routerMarkedUncertain: true }),
  ]);
  assert.equal(report.summary.routingPagesUncertain, 2);
  assert.equal(report.summary.routingPagesUnrouted, 1);
  assert.equal(report.summary.routingPagesWithoutText, 1);
});

test("retains approximate page image-region bounds in the coverage report", () => {
  const imageRegions = [{ id: "doc:page:4:image:1", bbox: { x: 12, y: 8, width: 64, height: 72 }, areaRatio: 0.31, ocrDisposition: "no-text-found" }];
  const report = buildCoverageReport([record(4, { hasRasterImageContent: true, imageRegions })]);
  assert.deepEqual(report.pages[0].imageRegions, imageRegions);
});

test("lists source table rows with disposition and page-relative evidence boxes", () => {
  const rows = [
    { cells: ["Heading", ""], cellBoxes: [{ x: 10, y: 10, width: 20, height: 5 }, null], bbox: { x: 10, y: 10, width: 20, height: 5 } },
    { cells: ["Parameter", "Required Specification"], cellBoxes: [null, null], bbox: { x: 0, y: 0, width: 1, height: 1 } },
    { cells: ["Grip distance", "0 to 100 mm"], cellBoxes: [{ x: 20, y: 30, width: 30, height: 8 }, { x: 70, y: 31, width: 50, height: 7 }], bbox: { x: 20, y: 30, width: 30, height: 8 } },
    { cells: ["", "   "], cellBoxes: [null, null], bbox: { x: 0, y: 0, width: 1, height: 1 } },
  ];
  const result = collectSourceTableCoverageRows(rows, new Map([[0, 1]]), new Set([1]), { width: 200, height: 100 });

  assert.equal(result.count, 1);
  assert.equal(result.notShown, 0);
  assert.deepEqual(result.rows[2], {
    rowNumber: 3,
    cells: ["Grip distance", "0 to 100 mm"],
    textTruncated: false,
    disposition: "unmapped",
    candidateSuggestions: 0,
    sourceMatchedCandidates: 0,
    matchedRequirementIds: [],
    acceptedLinkStatus: "no_candidate_suggestions",
    semanticCoverageStatus: "not_assessed",
    sourceClassification: "unclassified",
    classificationReason: "classification_unavailable",
    sourceElementIds: [],
    sourceTableId: null,
    sourceRowId: null,
    bbox: { x: 10, y: 30, width: 50, height: 8 },
  });
  assert.equal(result.rows[0].disposition, "candidate");
  assert.equal(result.rows[1].disposition, "header");
  assert.equal(result.rows[3].disposition, "empty");
});

test("links source table rows to accepted requirements and keeps partial citation matches explicit", () => {
  const rows = collectSourceTableCoverageRows([
    {
      cells: ["Operating pressure", "At least 10 bar; tolerance ±1 bar"],
      cellBoxes: [null, null],
      bbox: { x: 10, y: 10, width: 100, height: 12 },
      sourceTableId: "table-1",
      sourceRowId: "row-1",
      sourceClassification: "requirement",
      classificationReason: "technical_obligation",
      sourceElementIds: ["table-1", "row-1", "cell-1", "cell-2"],
    },
    { cells: ["Warranty", "Five years"], cellBoxes: [null, null], bbox: { x: 10, y: 30, width: 100, height: 12 }, sourceTableId: "table-1", sourceRowId: "row-2", sourceClassification: "requirement", classificationReason: "technical_obligation", sourceElementIds: ["table-1", "row-2", "cell-3", "cell-4"] },
  ], new Map([[0, 2]]), new Set(), { width: 200, height: 100 });
  const linked = linkSourceRowsToRequirements(rows.rows, 4, [
    { id: "req-10", page: 4, sourceRowIndex: 0, sourceElementIds: ["table-1", "row-1", "cell-2"] },
    { id: "req-11", page: 4, sourceElementIds: ["cell-4"] },
    { id: "table-only", page: 4, sourceElementIds: ["table-1"] },
    { id: "req-other-page", page: 5, sourceRowIndex: 0, sourceElementIds: ["row-1"] },
  ]);

  assert.deepEqual(linked[0].matchedRequirementIds, ["req-10"]);
  assert.equal(linked[0].sourceMatchedCandidates, 1);
  assert.equal(linked[0].acceptedLinkStatus, "linked");
  assert.equal(linked[0].semanticCoverageStatus, "not_assessed");
  assert.deepEqual(linked[0].sourceElementIds, ["table-1", "row-1", "cell-1", "cell-2"]);
  assert.equal(linked[0].sourceClassification, "requirement");
  assert.equal(linked[0].classificationReason, "technical_obligation");
  assert.deepEqual(linked[1].matchedRequirementIds, ["req-11"]);
  assert.equal(linked[1].acceptedLinkStatus, "linked");
  assert.equal(linked[1].semanticCoverageStatus, "not_assessed");
  assert.deepEqual(linked[1].matchedRequirementIds, ["req-11"]);
});

test("keeps the total unmapped-row count when detail previews are capped", () => {
  const rows = Array.from({ length: 12 }, (_, index) => ({
    cells: [`unmapped ${index + 1}`],
    cellBoxes: [null],
    bbox: { x: 1, y: index * 5, width: 20, height: 4 },
  }));
  const result = collectSourceTableCoverageRows(rows, new Map(rows.map((_, index) => [index, 1])), new Set(), { width: 100, height: 100 }, 10);

  assert.equal(result.rows.length, 10);
  assert.equal(result.notShown, 2);
  assert.equal(result.count, 0);
});
