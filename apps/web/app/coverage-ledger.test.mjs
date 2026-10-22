import test from "node:test";
import assert from "node:assert/strict";
import { buildCoverageReport } from "./coverage-ledger.ts";

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
  ...overrides,
});

test("summarizes document and selected-page coverage without calling unrun audits complete", () => {
  const report = buildCoverageReport([
    record(3, { sourceTableRowsDetected: 14, sourceTableRowsMappedToCandidates: 9, sourceTableRowsExcludedAsHeaders: 2, sourceTableRowsEmpty: 1, sourceTableRowsUnmapped: 2, auditStatus: "no_gaps_reported" }),
    record(1, { selectableTextAvailable: false, routingInputIncluded: false, selectedForExtraction: false, extractionStatus: "not_selected", ocrNeeded: true, sourceTableRowsDetected: null, candidateSuggestions: 0, sourceMatchedRows: 0, sourceMatchedRequirements: 0, needsHumanReview: 0, rejectedSuggestions: 0, rejectionReasons: [], auditStatus: "not_run" }),
    record(2, { selectedForExtraction: false, extractionStatus: "not_selected", routingContextClipped: true, sourceTableRowsDetected: 0, sourceTableRowsMappedToCandidates: 0, sourceTableRowsExcludedAsHeaders: 0, sourceTableRowsEmpty: 0, sourceTableRowsUnmapped: 0, candidateSuggestions: 0, sourceMatchedRows: 0, sourceMatchedRequirements: 0, needsHumanReview: 0, rejectedSuggestions: 0, rejectionReasons: [], auditStatus: "incomplete" }),
  ]);

  assert.deepEqual(report.pages.map((page) => page.page), [1, 2, 3]);
  assert.equal(report.summary.documentPages, 3);
  assert.equal(report.summary.routingPages, 2);
  assert.equal(report.summary.selectedTechnicalPages, 1);
  assert.equal(report.summary.pagesWithoutSelectableText, 1);
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
