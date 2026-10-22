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

test("preserves every source column for an explicit multi-column compliance report", () => {
  const sheet = buildResponseSheet({
    sourceColumns: [
      { header: "S. No.", role: "serial" },
      { header: "Specification", role: "heading" },
      { header: "Description", role: "specification" },
      { header: "Comply (Yes/No)", role: "compliance" },
      { header: "Remarks/Justifications", role: "remark" },
    ],
    extractionMode: "visual-compliance-sheet",
    requirements: [
      { id: "req-1", text: "≥ 300 mm", quote: "≥ 300 mm", sourceCells: ["3", "Thickness", "≥ 300 mm", "", ""], page: 20 },
      { id: "req-2", text: "≥ 4 mm", quote: "≥ 4 mm", sourceCells: ["4", "Top skin thickness", "≥ 4 mm", "", ""], page: 20 },
    ],
  });
  assert.deepEqual(sheet.columns.map((column) => column.header), [
    "S. No.", "Specification", "Description", "Comply (Yes/No)", "Remarks/Justifications", "Source page",
  ]);
  assert.deepEqual(sheet.rows.map((row) => row.values), [
    ["3", "Thickness", "≥ 300 mm", "", "", "Page 20"],
    ["4", "Top skin thickness", "≥ 4 mm", "", "", "Page 20"],
  ]);
});

test("merges blank page continuations but keeps a numbered requirement on the next page separate", () => {
  const sheet = buildResponseSheet({
    sourceColumns: [
      { header: "S. No.", role: "serial" },
      { header: "Specification", role: "heading" },
      { header: "Description", role: "specification" },
    ],
    extractionMode: "visual-compliance-sheet",
    requirements: [
      { id: "req-3", text: "6 EA", quote: "6 EA", sourceCells: ["3", "Number of Isolators", "6 EA"], page: 23 },
      { id: "req-5", text: "1.5 Hz or lower", quote: "1.5 Hz or lower", sourceCells: ["5", "Vertical Isolation, Resonance", "1.5 Hz or lower"], page: 24, continuationOfPrevious: true },
      { id: "req-10", text: "The service requirement starts here.", quote: "The service requirement starts here.", sourceCells: ["10", "Service", "The service requirement starts here."], page: 25 },
      { id: "req-11", text: "warranty will be extended accordingly.", quote: "warranty will be extended accordingly.", sourceCells: ["", "", "warranty will be extended accordingly."], page: 26, continuationOfPrevious: true },
    ],
  });
  assert.equal(sheet.rows.length, 3);
  assert.deepEqual(sheet.rows.slice(0, 2).map((row) => row.values.slice(0, 3)), [
    ["3", "Number of Isolators", "6 EA"],
    ["5", "Vertical Isolation, Resonance", "1.5 Hz or lower"],
  ]);
  assert.deepEqual(sheet.rows[2].values.slice(0, 3), [
    "10", "Service", "The service requirement starts here. warranty will be extended accordingly.",
  ]);
  assert.equal(sheet.rows[2].values.at(-1), "Pages 25 and 26");
  assert.deepEqual(sheet.rows[2].sourceRequirementIds, ["req-10", "req-11"]);
});
