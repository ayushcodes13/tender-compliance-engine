import test from "node:test";
import assert from "node:assert/strict";
import { buildResponseSheet, removeResponseSheetRow, updateResponseSheetCell } from "./response-sheet.ts";

const structured = {
  extractionMode: "structured-table",
  requirements: [{
    id: "req-1", text: "Universal Testing Machine", parameter: "Universal Testing Machine (300 kN)",
    quote: "High performance • auto ranging", specifications: ["High performance", "Auto ranging"], page: 17,
  }],
};

test("builds one editable response row per structured subpoint and preserves shared heading", () => {
  const sheet = buildResponseSheet(structured);
  assert.equal(sheet.rows.length, 2);
  assert.deepEqual(sheet.rows.map((row) => row.values[0]), ["Universal Testing Machine (300 kN)", "Universal Testing Machine (300 kN)"]);
  assert.deepEqual(sheet.rows.map((row) => row.values[1]), ["High performance", "Auto ranging"]);
  assert.deepEqual(sheet.rows.map((row) => row.values.at(-1)), ["Page 17", "Page 17"]);
});

test("edits one exported cell without changing its source identity or citation", () => {
  const sheet = buildResponseSheet(structured);
  const edited = updateResponseSheetCell(sheet, sheet.rows[1].id, 1, "Auto ranging force readout");
  assert.equal(edited.rows[1].values[1], "Auto ranging force readout");
  assert.equal(edited.rows[0].values[1], "High performance");
  assert.equal(edited.rows[1].sourceRequirementId, "req-1");
  assert.equal(edited.rows[1].values.at(-1), "Page 17");
});

test("editing a shared heading updates every row in that contiguous group", () => {
  const sheet = buildResponseSheet(structured);
  const edited = updateResponseSheetCell(sheet, sheet.rows[0].id, 0, "UTM 300 kN");
  assert.deepEqual(edited.rows.map((row) => row.values[0]), ["UTM 300 kN", "UTM 300 kN"]);
});

test("source page cells cannot be edited and removed rows leave the original sheet intact", () => {
  const sheet = buildResponseSheet(structured);
  const lastColumn = sheet.columns.length - 1;
  const unchanged = updateResponseSheetCell(sheet, sheet.rows[0].id, lastColumn, "Page 99");
  assert.equal(unchanged.rows[0].values[lastColumn], "Page 17");
  const reduced = removeResponseSheetRow(sheet, sheet.rows[0].id);
  assert.equal(reduced.rows.length, 1);
  assert.equal(sheet.rows.length, 2);
});

test("keeps source-defined columns and creates distinct IDs for split requirement rows", () => {
  const sheet = buildResponseSheet({
    sourceColumns: [
      { header: "Heading", role: "heading" },
      { header: "Technical Parameters", role: "specification" },
      { header: "Remarks", role: "remark" },
    ],
    requirements: [{ id: "req-2", text: "Product performance • accuracy", headingPrefix: "Product", quote: "Product performance • accuracy", page: 8 }],
  });
  assert.deepEqual(sheet.columns.map((column) => column.header), ["Heading", "Technical Parameters", "Remarks", "Source page"]);
  assert.equal(sheet.rows.length, 2);
  assert.notEqual(sheet.rows[0].id, sheet.rows[1].id);
  assert.deepEqual(sheet.rows.map((row) => row.values[1]), ["performance", "• accuracy"]);
});
