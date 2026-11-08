import test from "node:test";
import assert from "node:assert/strict";
import {
  extractNumericConstraint,
  compareNumericConstraints,
  findProductEvidence,
  evaluateRowCompliance,
  evaluateSheetCompliance,
  projectComplianceReportToSheet,
} from "./oem-compliance-engine.ts";

test("extracts numerical constraints from text correctly", () => {
  const tol = extractNumericConstraint("Salinity measurement accuracy ±0.002 PSU");
  assert.equal(tol?.kind, "tolerance");
  assert.equal(tol?.tolerance, 0.002);
  assert.equal(tol?.unit, "psu");

  const range = extractNumericConstraint("Conductivity range 0 to 70 mS/cm");
  assert.equal(range?.kind, "range");
  assert.equal(range?.min, 0);
  assert.equal(range?.max, 70);
  assert.equal(range?.unit, "ms/cm");

  const minVal = extractNumericConstraint("Battery backup minimum 4 hours");
  assert.equal(minVal?.kind, "min");
  assert.equal(minVal?.min, 4);
  assert.equal(minVal?.unit, "hours");

  const maxVal = extractNumericConstraint("Weight up to 15 kg");
  assert.equal(maxVal?.kind, "max");
  assert.equal(maxVal?.max, 15);
  assert.equal(maxVal?.unit, "kg");
});

test("evaluates tolerance / accuracy deterministically", () => {
  const tenderTol = { kind: "tolerance", value: 0, tolerance: 0.003, unit: "psu" };

  // Better tolerance (0.002 <= 0.003) -> COMPLIED
  const better = compareNumericConstraints(tenderTol, { kind: "tolerance", value: 0, tolerance: 0.002, unit: "psu" });
  assert.equal(better.status, "COMPLIED");
  assert.match(better.reason, /complies with or exceeds/i);

  // Equal tolerance (0.003 <= 0.003) -> COMPLIED
  const equal = compareNumericConstraints(tenderTol, { kind: "tolerance", value: 0, tolerance: 0.003, unit: "psu" });
  assert.equal(equal.status, "COMPLIED");

  // Worse tolerance (0.005 > 0.003) -> DEVIATION
  const worse = compareNumericConstraints(tenderTol, { kind: "tolerance", value: 0, tolerance: 0.005, unit: "psu" });
  assert.equal(worse.status, "DEVIATION");
  assert.match(worse.reason, /wider than required/i);
});

test("evaluates measurement ranges deterministically", () => {
  const tenderRange = { kind: "range", min: 0, max: 60, unit: "ms/cm" };

  // Wider range encompassing tender (0 to 70 covers 0 to 60) -> COMPLIED
  const wider = compareNumericConstraints(tenderRange, { kind: "range", min: 0, max: 70, unit: "ms/cm" });
  assert.equal(wider.status, "COMPLIED");

  // Narrower range (10 to 50 does not cover 0 to 60) -> DEVIATION
  const narrower = compareNumericConstraints(tenderRange, { kind: "range", min: 10, max: 50, unit: "ms/cm" });
  assert.equal(narrower.status, "DEVIATION");
});

test("distinguishes missing evidence from contradictory evidence", () => {
  const mockProductDoc = {
    id: "doc-oem-1",
    name: "Salinometer-Datasheet.pdf",
    pageCount: 3,
    pages: [
      {
        pageNumber: 1,
        text: "The Auto Salinometer features high precision conductivity measurement with accuracy ±0.002 PSU. Includes digital readout unit.",
        lines: [
          { text: "Accuracy ±0.002 PSU", bbox: { x: 10, y: 30, width: 40, height: 5 } },
          { text: "Digital readout unit included", bbox: { x: 10, y: 40, width: 50, height: 5 } },
        ],
      },
      {
        pageNumber: 2,
        text: "Standard interface RS-232 and USB port provided. Power supply 230 V 50 Hz.",
      },
    ],
  };

  // 1. Found specification -> COMPLIED with exact product citation
  const row1 = { id: "row-1", sourceRequirementId: "req-1", values: ["Salinity accuracy ±0.003 PSU"], sourceRequirementIds: ["req-1"] };
  const res1 = evaluateRowCompliance(row1, "Salinity accuracy ±0.003 PSU", { page: 18, quote: "Salinity accuracy ±0.003 PSU", bbox: null }, mockProductDoc);
  assert.equal(res1.status, "COMPLIED");
  assert.ok(res1.productCitation);
  assert.equal(res1.productCitation.page, 1);
  assert.match(res1.productCitation.quote, /±0.002 PSU/);

  // 2. Missing evidence (transit case not in doc) -> INSUFFICIENT_EVIDENCE, requires human review
  const row2 = { id: "row-2", sourceRequirementId: "req-2", values: ["Ruggedized transit case with foam"], sourceRequirementIds: ["req-2"] };
  const res2 = evaluateRowCompliance(row2, "Ruggedized transit case with foam", { page: 20, quote: "Transit case", bbox: null }, mockProductDoc);
  assert.equal(res2.status, "INSUFFICIENT_EVIDENCE");
  assert.equal(res2.requiresHumanReview, true);
  assert.equal(res2.productCitation, null);
  assert.match(res2.reason, /no matching specification/i);
});

test("evaluates full compliance sheet and computes accurate summary", () => {
  const mockProductDoc = {
    id: "doc-oem-1",
    name: "Product-Spec.pdf",
    pageCount: 2,
    pages: [
      {
        pageNumber: 1,
        text: "Digital readout unit standard. Battery backup 6 hours. RS-232 interface.",
      },
      {
        pageNumber: 2,
        text: "Weight 18 kg. Analog output optional.",
      },
    ],
  };

  const sheet = {
    columns: [{ header: "Spec", role: "specification" }],
    rows: [
      { id: "r1", values: ["Digital readout unit"], sourceRequirementId: "t1", sourceRequirementIds: ["t1"] },
      { id: "r2", values: ["Battery backup minimum 4 hours"], sourceRequirementId: "t2", sourceRequirementIds: ["t2"] },
      { id: "r3", values: ["Weight up to 15 kg"], sourceRequirementId: "t3", sourceRequirementIds: ["t3"] },
      { id: "r4", values: ["Underwater pressure housing 6000m"], sourceRequirementId: "t4", sourceRequirementIds: ["t4"] },
    ],
  };

  const tenderRequirements = [
    { id: "t1", page: 18, quote: "Digital readout unit", bbox: null },
    { id: "t2", page: 18, quote: "Battery backup min 4 hours", bbox: null },
    { id: "t3", page: 19, quote: "Weight max 15 kg", bbox: null },
    { id: "t4", page: 20, quote: "Underwater housing", bbox: null },
  ];

  const report = evaluateSheetCompliance(sheet, tenderRequirements, mockProductDoc, "Tender Compliance Matrix");
  assert.equal(report.summary.totalRows, 4);
  assert.equal(report.summary.complied, 2); // Digital readout, Battery backup (6 >= 4)
  assert.equal(report.summary.deviation, 1); // Weight 18kg > 15kg
  assert.equal(report.summary.insufficientEvidence, 1); // Underwater housing not found
  assert.equal(report.assessments.length, 4);

  const projected = projectComplianceReportToSheet(sheet, report);
  assert.equal(projected.columns.length, 6);
  assert.equal(projected.rows.length, 4);
  assert.equal(projected.rows[0].values[2], "Complied");
  assert.match(projected.rows[0].values[3], /Digital readout unit/);
  assert.match(projected.rows[0].values[4], /Product-Spec.pdf \(p. 1\)/);
});
