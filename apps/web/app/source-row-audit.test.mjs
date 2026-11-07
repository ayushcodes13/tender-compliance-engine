import test from "node:test";
import assert from "node:assert/strict";
import { batchSourceRowsForAudit, isSourceRowAuditBatchWithinLimits, validateSourceRowAuditResult } from "./source-row-audit.ts";

test("batches source rows within row and character limits while retaining oversized rows alone", () => {
  const rows = [
    { rowIndex: 0, sourceText: "a".repeat(4), extractedRequirements: [] },
    { rowIndex: 1, sourceText: "b".repeat(4), extractedRequirements: [] },
    { rowIndex: 2, sourceText: "c".repeat(11), extractedRequirements: [] },
    { rowIndex: 3, sourceText: "d", extractedRequirements: [] },
  ];
  const batches = batchSourceRowsForAudit(rows, { maxRows: 2, maxChars: 8 });
  assert.deepEqual(batches.map((batch) => batch.map((row) => row.rowIndex)), [[0, 1], [2], [3]]);
  assert.equal(isSourceRowAuditBatchWithinLimits(batches[0], { maxRows: 2, maxChars: 8 }), true);
  assert.equal(isSourceRowAuditBatchWithinLimits(batches[1], { maxRows: 2, maxChars: 8 }), false);
  assert.deepEqual(batchSourceRowsForAudit(rows, { maxRows: 0 }), []);
});

test("accepts exactly one bounded semantic disposition for every requested source row", () => {
  assert.deepEqual(validateSourceRowAuditResult({ rows: [
    { row_index: 4, status: "possible_gap", note: "Two limits appear combined." },
    { row_index: 8, status: "no_gap_reported", note: "" },
  ] }, [4, 8]), {
    complete: true,
    rows: [
      { rowIndex: 4, status: "possible_gap", note: "Two limits appear combined." },
      { rowIndex: 8, status: "no_gap_reported", note: "" },
    ],
  });
});

test("rejects missing, duplicate, out-of-batch, unknown, or oversized audit results", () => {
  for (const value of [
    null,
    { rows: [{ row_index: 1, status: "no_gap_reported", note: "" }] },
    { rows: [{ row_index: 1, status: "no_gap_reported", note: "" }, { row_index: 1, status: "ambiguous", note: "" }] },
    { rows: [{ row_index: 3, status: "no_gap_reported", note: "" }, { row_index: 1, status: "no_gap_reported", note: "" }] },
    { rows: [{ row_index: 1, status: "complete", note: "" }, { row_index: 2, status: "no_gap_reported", note: "" }] },
    { rows: [{ row_index: 1, status: "no_gap_reported", note: "x".repeat(501) }, { row_index: 2, status: "no_gap_reported", note: "" }] },
  ]) assert.equal(validateSourceRowAuditResult(value, [1, 2]).complete, false);
});
