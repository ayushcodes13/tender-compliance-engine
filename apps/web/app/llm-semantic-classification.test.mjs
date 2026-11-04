import test from "node:test";
import assert from "node:assert/strict";

test("LLM semantic classification distinguishes requirements from instructions and headers", () => {
  const candidates = [
    { page: 1, quote: "Dimensions: length 3000 mm or more, width 1500 mm or more", row_type: "requirement", category: "Mechanical" },
    { page: 1, quote: "Top skin thickness ≥ 4 mm ferromagnetic stainless steel", row_type: "requirement", category: "Mechanical" },
    { page: 1, quote: "A. T - SHAPE Optical Table System", row_type: "section", category: "Other" },
    { page: 1, quote: "(Indicate Compliance Status (Yes/No) for each and every point)", row_type: "instruction", category: "Other" },
    { page: 2, quote: "All points indicated above (Annexure - II) must be filled by the bidder and relevant documents (i.e. catalogue, literature etc.) should be submitted.", row_type: "instruction", category: "Other" },
    { page: 2, quote: "Quote must have a technical compliance report as prescribed in Annexure - II.", row_type: "instruction", category: "Other" },
    { page: 2, quote: "Specification | Description | Comply (Yes/No) | Any deviation | Remarks", row_type: "header", category: "Other" },
  ];

  const accepted = [];
  const rejected = [];

  for (const candidate of candidates) {
    if (candidate.row_type === "instruction" || candidate.row_type === "header") {
      rejected.push({ quote: candidate.quote, reason: "administrative_procurement_clause" });
    } else {
      accepted.push(candidate);
    }
  }

  assert.equal(accepted.length, 3);
  assert.deepEqual(accepted.map((c) => c.quote), [
    "Dimensions: length 3000 mm or more, width 1500 mm or more",
    "Top skin thickness ≥ 4 mm ferromagnetic stainless steel",
    "A. T - SHAPE Optical Table System",
  ]);

  assert.equal(rejected.length, 4);
  assert.ok(rejected.some((r) => r.quote.includes("Indicate Compliance Status")));
  assert.ok(rejected.some((r) => r.quote.includes("filled by the bidder")));
  assert.ok(rejected.some((r) => r.quote.includes("technical compliance report")));
  assert.ok(rejected.some((r) => r.quote.includes("Specification | Description")));
  assert.ok(rejected.every((r) => r.reason === "administrative_procurement_clause"));
});

test("vector table rows classified as header or instruction are omitted from response requirements", () => {
  const modelLabels = new Map([
    [0, { row_index: 0, row_type: "header" }],
    [1, { row_index: 1, row_type: "instruction" }],
    [2, { row_index: 2, row_type: "section" }],
    [3, { row_index: 3, row_type: "requirement" }],
  ]);

  const sourceRows = [
    { cells: ["Specification", "Description", "Comply (Yes/No)", "Remarks"] },
    { cells: ["(Indicate Compliance Status (Yes/No) for each and every point)", "", "", ""] },
    { cells: ["A. T - SHAPE Optical Table System", "", "", ""] },
    { cells: ["Dimensions", "3000 mm x 1500 mm", "", ""] },
  ];

  const emitted = [];
  const excludedIndices = new Set();

  sourceRows.forEach((row, index) => {
    const label = modelLabels.get(index);
    if (label?.row_type === "header" || label?.row_type === "instruction") {
      excludedIndices.add(index);
      return;
    }
    emitted.push({ index, rowType: label?.row_type, quote: row.cells[0] });
  });

  assert.equal(excludedIndices.has(0), true, "Column header row is excluded");
  assert.equal(excludedIndices.has(1), true, "Instruction row is excluded");
  assert.equal(emitted.length, 2);
  assert.equal(emitted[0].rowType, "section");
  assert.equal(emitted[1].rowType, "requirement");
});
