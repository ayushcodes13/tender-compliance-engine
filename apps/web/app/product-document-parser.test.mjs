import test from "node:test";
import assert from "node:assert/strict";
import { getSampleProductDocument, getSampleProductFile } from "./product-document-parser.ts";
import { evaluateSheetCompliance } from "./oem-compliance-engine.ts";

test("creates valid in-memory sample product PDF file", () => {
  const file = getSampleProductFile();
  assert.equal(file.name, "Auto-Salinometer-Model-8400C-Datasheet.pdf");
  assert.equal(file.type, "application/pdf");
  assert.ok(file.size > 500);
});

test("provides structured sample product document with pages and bounding boxes", () => {
  const doc = getSampleProductDocument();
  assert.equal(doc.id, "sample-salinometer-oem");
  assert.equal(doc.pageCount, 3);
  assert.equal(doc.pages.length, 3);

  // Page 1 has Salinity accuracy and Digital readout
  const page1 = doc.pages[0];
  assert.equal(page1.pageNumber, 1);
  assert.match(page1.text, /±0.002 PSU/);
  assert.match(page1.text, /Digital readout unit/);
  assert.ok(page1.lines && page1.lines.length > 0);
  assert.ok(page1.lines[0].bbox);
});

test("evaluates sample product document against typical salinometer tender requirements", () => {
  const doc = getSampleProductDocument();

  const sheet = {
    columns: [{ header: "Specification", role: "specification" }],
    rows: [
      { id: "r1", values: ["Salinity accuracy ±0.003 PSU or better"], sourceRequirementId: "req-1", sourceRequirementIds: ["req-1"] },
      { id: "r2", values: ["Digital readout unit with display"], sourceRequirementId: "req-2", sourceRequirementIds: ["req-2"] },
      { id: "r3", values: ["Computer interface RS-232 and USB port"], sourceRequirementId: "req-3", sourceRequirementIds: ["req-3"] },
      { id: "r4", values: ["Total instrument weight max 15 kg"], sourceRequirementId: "req-4", sourceRequirementIds: ["req-4"] },
      { id: "r5", values: ["Heavy duty wooden packing case with foam"], sourceRequirementId: "req-5", sourceRequirementIds: ["req-5"] },
      { id: "r6", values: ["Submersible titanium housing depth rating 6000m"], sourceRequirementId: "req-6", sourceRequirementIds: ["req-6"] },
    ],
  };

  const tenderRequirements = [
    { id: "req-1", page: 18, quote: "Salinity accuracy ±0.003 PSU or better", bbox: null },
    { id: "req-2", page: 18, quote: "Digital readout unit with display", bbox: null },
    { id: "req-3", page: 18, quote: "Computer interface RS-232", bbox: null },
    { id: "req-4", page: 19, quote: "Total instrument weight max 15 kg", bbox: null },
    { id: "req-5", page: 20, quote: "Wooden packing case with foam", bbox: null },
    { id: "req-6", page: 20, quote: "Submersible titanium housing 6000m", bbox: null },
  ];

  const report = evaluateSheetCompliance(sheet, tenderRequirements, doc, "NIOT Auto Salinometer");
  assert.equal(report.summary.totalRows, 6);
  assert.equal(report.summary.complied, 5); // Accuracy (0.002 <= 0.003), Readout, Interface, Weight (14.5 <= 15), Packing case
  assert.equal(report.summary.insufficientEvidence, 1); // 6000m submersible housing not in lab salinometer datasheet
  assert.equal(report.assessments.length, 6);

  // Check two-sided citations
  const accuracyAssessment = report.assessments[0];
  assert.equal(accuracyAssessment.status, "COMPLIED");
  assert.equal(accuracyAssessment.tenderCitation.page, 18);
  assert.equal(accuracyAssessment.productCitation?.page, 1);
  assert.match(accuracyAssessment.productCitation?.quote || "", /±0.002 PSU/);
});
