import assert from "node:assert/strict";
import test from "node:test";
import { analysisExportFilename, deriveAnalysisCompletion } from "./analysis-completion.ts";

const inspected = (page, overrides = {}) => ({
  page,
  routingDisposition: "selected",
  routingReason: "Selected for technical review.",
  routerMarkedUncertain: false,
  selectedForExtraction: true,
  extractionStatus: "complete",
  ...overrides,
});
const excluded = {
  page: 2,
  routingDisposition: "excluded",
  routingReason: "Explicitly outside the technical specification section.",
  routerMarkedUncertain: false,
  selectedForExtraction: false,
  extractionStatus: "not_selected",
};

const assess = (overrides = {}) => deriveAnalysisCompletion({
  expectedPageCount: 2,
  pages: [inspected(1), excluded],
  plannedInspectionStates: ["executed"],
  hasPendingWork: false,
  coverageAuditIncomplete: false,
  roundBudgetExhausted: false,
  ...overrides,
});

test("completes only when every page has an inspected or explicit exclusion state and no work remains", () => {
  const result = assess();
  assert.equal(result.completionStatus, "complete");
  assert.deepEqual(result.pageTerminalStates.map(({ page, state }) => [page, state]), [[1, "inspected"], [2, "excluded"]]);
  assert.deepEqual(result.completionReasons, []);
});

test("keeps uncertain, failed, and unvisited pages partial", () => {
  const cases = [
    { ...inspected(1), routingDisposition: "uncertain", routerMarkedUncertain: true, routingReason: "Page scope is uncertain." },
    { ...inspected(1), extractionStatus: "incomplete" },
    { ...inspected(1), routingDisposition: "unrouted", selectedForExtraction: false, extractionStatus: "not_selected" },
  ];
  const assessments = cases.map((page) => assess({ pages: [page, excluded] }));
  assert.deepEqual(assessments.map((result) => result.completionStatus), ["partial", "partial", "partial"]);
  assert.deepEqual(assessments.map((result) => result.pageTerminalStates[0].state), ["uncertain", "failed", "unvisited"]);
});

test("does not accept an exclusion without a reason as a terminal exclusion", () => {
  const result = assess({ pages: [inspected(1), { ...excluded, routingReason: "   " }] });
  assert.equal(result.completionStatus, "partial");
  assert.equal(result.pageTerminalStates[1].state, "uncertain");
});

test("keeps unsupported, deferred, pending, incomplete-audit, and budget-exhausted runs partial", () => {
  assert.equal(assess({ plannedInspectionStates: ["unsupported"] }).completionStatus, "partial");
  assert.equal(assess({ plannedInspectionStates: ["deferred_to_legacy"] }).completionStatus, "partial");
  assert.equal(assess({ hasPendingWork: true }).completionStatus, "partial");
  assert.equal(assess({ coverageAuditIncomplete: true }).completionStatus, "partial");
  assert.equal(assess({ roundBudgetExhausted: true }).completionStatus, "partial");
});

test("missing or duplicate page states fail closed", () => {
  assert.equal(assess({ expectedPageCount: 3 }).completionStatus, "partial");
  assert.equal(assess({ pages: [inspected(1), inspected(1)] }).completionStatus, "partial");
});

test("partial analysis export filenames are visibly labeled", () => {
  assert.equal(analysisExportFilename("tender.pdf", "partial", "xlsx"), "tender-partial-draft.xlsx");
  assert.equal(analysisExportFilename("tender.pdf", "complete", "docx"), "tender-technical-response.docx");
});
