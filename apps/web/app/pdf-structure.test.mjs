import test from "node:test";
import assert from "node:assert/strict";
import { extractStructuredTechnicalSection } from "./pdf-structure.ts";

const item = (str, x, y) => ({ str, x, y, box: { x, y: 1000 - y, width: Math.max(2, str.length * 4), height: 8 } });
const cell = (x, y, width, height) => ({ x, y, width, height });

test("groups a technical table by parameter, retains empty rows, and carries the following bullet list", () => {
  const items = [
    item("Section 4 – Technical specifications", 10, 430),
    item("Technical requirements of the Diamond Scriber", 10, 400),
    item("Parameter", 20, 310),
    item("Required Specification", 110, 310),
    item("Wafer Chuck (1 number)", 20, 265),
    item("•", 105, 265),
    item("Vacuum-backed chuck", 120, 265),
    item("•", 105, 253),
    item("XY movement range minimum 25 mm", 120, 253),
    item("with digital readout", 120, 241),
    item("Special pliers for wafer breaking (1 set)", 20, 215),
    item("Other requirements:", 10, 180),
    item("•", 10, 160),
    item("Maintenance for at least 3 years", 30, 160),
    item("including service visits", 30, 150),
    item("•", 10, 140),
    item("Training after installation", 30, 140),
  ];
  const rectangles = [
    cell(10, 300, 90, 20), cell(100, 300, 200, 20),
    cell(10, 240, 90, 45), cell(100, 240, 200, 45),
    cell(10, 200, 90, 30), cell(100, 200, 200, 30),
  ];

  const result = extractStructuredTechnicalSection(items, rectangles);

  assert.equal(result.sectionTitle, "Section 4 – Technical specifications");
  assert.equal(result.sectionHeading, "Technical requirements of the Diamond Scriber");
  assert.deepEqual(result.requirements.map((row) => row.parameter), [
    "Wafer Chuck (1 number)",
    "Special pliers for wafer breaking (1 set)",
    "Other requirements",
  ]);
  assert.deepEqual(result.requirements[0].specifications, [
    "Vacuum-backed chuck",
    "XY movement range minimum 25 mm with digital readout",
  ]);
  assert.match(result.requirements[0].quote, /25 mm/);
  assert.deepEqual(result.requirements[1].specifications, []);
  assert.equal(result.requirements[1].quote, "Special pliers for wafer breaking (1 set)");
  assert.deepEqual(result.requirements[2].specifications, [
    "Maintenance for at least 3 years including service visits",
    "Training after installation",
  ]);
  assert.match(result.requirements[2].quote, /^• Maintenance/);
  assert.ok(result.requirements.every((row) => row.bbox.width > 0 && row.bbox.height > 0));
});

test("does not infer a structured table without both named headers and cell geometry", () => {
  const items = [item("Parameter", 20, 310), item("Required Specification", 110, 310)];
  assert.equal(extractStructuredTechnicalSection(items, []), null);
  assert.equal(extractStructuredTechnicalSection(items, [cell(10, 300, 90, 20), cell(100, 300, 200, 20)]), null);
  assert.equal(extractStructuredTechnicalSection([item("Specification", 20, 310)], [cell(10, 300, 90, 20)]), null);
});
