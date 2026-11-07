import test from "node:test";
import assert from "node:assert/strict";
import { batchSourceRowsForAudit, isSourceRowAuditBatchWithinLimits, validateSourceRowAuditResult } from "./source-row-audit.ts";

test("batches source rows within row and character limits while retaining oversized rows alone", () => {
  const rows = [
    { rowIndex: 0, sourceCells: ["a".repeat(4)], extractedRequirements: [] },
    { rowIndex: 1, sourceCells: ["b".repeat(4)], extractedRequirements: [] },
    { rowIndex: 2, sourceCells: ["c".repeat(11)], extractedRequirements: [] },
    { rowIndex: 3, sourceCells: ["d"], extractedRequirements: [] },
  ];
  const batches = batchSourceRowsForAudit(rows, { maxRows: 2, maxChars: 8 });
  assert.deepEqual(batches.map((batch) => batch.map((row) => row.rowIndex)), [[0, 1], [2], [3]]);
  assert.equal(isSourceRowAuditBatchWithinLimits(batches[0], { maxRows: 2, maxChars: 8 }), true);
  assert.equal(isSourceRowAuditBatchWithinLimits(batches[1], { maxRows: 2, maxChars: 8 }), false);
  assert.deepEqual(batchSourceRowsForAudit(rows, { maxRows: 0 }), []);
});

test("accepts exactly one bounded semantic disposition for every requested source row", () => {
  assert.deepEqual(validateSourceRowAuditResult({ rows: [
    { row_index: 4, status: "possible_gap", note: "Second limit missing.", missing_source_quotes: ["Output shall be at least 20 kW."] },
    { row_index: 8, status: "no_gap_reported", note: "", missing_source_quotes: [] },
  ] }, [4, 8], [
    { rowIndex: 4, sourceCells: ["Output shall be 10 kW. Output shall be at least 20 kW."], extractedRequirements: ["Output shall be 10 kW."] },
    { rowIndex: 8, sourceCells: ["Housing shall be stainless steel."], extractedRequirements: ["Housing shall be stainless steel."] },
  ]), {
    complete: true,
    rows: [
      { rowIndex: 4, status: "possible_gap", note: "Second limit missing.", missingSourceQuotes: ["Output shall be at least 20 kW."] },
      { rowIndex: 8, status: "no_gap_reported", note: "", missingSourceQuotes: [] },
    ],
  });
});

test("rejects missing, duplicate, out-of-batch, unknown, or oversized audit results", () => {
  for (const value of [
    null,
    { rows: [{ row_index: 1, status: "no_gap_reported", note: "", missing_source_quotes: [] }] },
    { rows: [{ row_index: 1, status: "no_gap_reported", note: "", missing_source_quotes: [] }, { row_index: 1, status: "ambiguous", note: "", missing_source_quotes: [] }] },
    { rows: [{ row_index: 3, status: "no_gap_reported", note: "", missing_source_quotes: [] }, { row_index: 1, status: "no_gap_reported", note: "", missing_source_quotes: [] }] },
    { rows: [{ row_index: 1, status: "complete", note: "", missing_source_quotes: [] }, { row_index: 2, status: "no_gap_reported", note: "", missing_source_quotes: [] }] },
    { rows: [{ row_index: 1, status: "no_gap_reported", note: "x".repeat(501), missing_source_quotes: [] }, { row_index: 2, status: "no_gap_reported", note: "", missing_source_quotes: [] }] },
  ]) assert.equal(validateSourceRowAuditResult(value, [1, 2]).complete, false);
});

test("rejects paraphrases and recovery quotes on non-gap dispositions", () => {
  const sourceRows = [{ rowIndex: 1, sourceCells: ["Pressure shall exceed 20 bar."], extractedRequirements: [] }];
  for (const result of [
    { rows: [{ row_index: 1, status: "possible_gap", note: "", missing_source_quotes: ["Pressure must be above 20 bar."] }] },
    { rows: [{ row_index: 1, status: "no_gap_reported", note: "", missing_source_quotes: ["Pressure shall exceed 20 bar."] }] },
  ]) assert.equal(validateSourceRowAuditResult(result, [1], sourceRows).complete, false);
});
