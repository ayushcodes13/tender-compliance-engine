import test from "node:test";
import assert from "node:assert/strict";
import { buildCoverageReport, collectSourceTableCoverageRows, describeRejectedSuggestion } from "./coverage-ledger.ts";

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
    bbox: { x: 10, y: 30, width: 50, height: 8 },
  });
  assert.equal(result.rows[0].disposition, "candidate");
  assert.equal(result.rows[1].disposition, "header");
  assert.equal(result.rows[3].disposition, "empty");
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
