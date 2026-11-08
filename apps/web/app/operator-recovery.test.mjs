import test from "node:test";
import assert from "node:assert/strict";
import { createOperatorPageReference, insertRequirementByPhysicalPage, recoverDocumentIdentity } from "./operator-recovery.ts";

const fingerprint = "a".repeat(64);
const document = {
  documentId: "doc-" + fingerprint.slice(0, 24),
  documentVersionId: "ver-" + fingerprint,
  documentFingerprint: fingerprint,
};
const source = {
  ...document,
  physicalPdfPageNumber: 18,
  sourceText: "Digital readout ≥ 1",
  sourceElementIds: ["page-18:text:3"],
  bbox: { x: 20, y: 30, width: 40, height: 10 },
  bboxCoordinateSystem: "pdfjs-viewport-scale-1",
  extractionMethod: "pdfjs-native-text",
  locationPrecision: "exact",
};

test("operator-entered requirement never masquerades as extracted PDF text", () => {
  const ref = createOperatorPageReference(document, 18);
  assert.equal(ref.physicalPdfPageNumber, 18);
  assert.equal(ref.sourceText, "");
  assert.equal(ref.extractionMethod, "operator-entered");
  assert.equal(ref.locationPrecision, "approximate");
  assert.deepEqual(ref.sourceElementIds, []);
  assert.equal(ref.bbox, null);
  assert.equal("startOffset" in ref, false);
  assert.equal("endOffset" in ref, false);
  assert.deepEqual(recoverDocumentIdentity(source, 25), { ...document, pageCount: 25, inventoryIntegrity: "unverified" });
});

test("diagnostic recovery uses the original PDF fingerprint and never fabricates an inventory verification", () => {
  const result = recoverDocumentIdentity(source, 25);
  assert.ok(result);
  assert.equal(result.documentFingerprint, fingerprint);
  assert.notEqual(result.documentFingerprint, "manual-recovery");
  assert.equal(result.inventoryIntegrity, "unverified");
  assert.equal(recoverDocumentIdentity({ ...source, documentId: "doc-fake" }, 25), null);
  assert.equal(recoverDocumentIdentity({ ...source, documentVersionId: "v-created-now" }, 25), null);
  assert.equal(recoverDocumentIdentity({ ...source, documentFingerprint: "manual-recovery" }, 25), null);
  assert.equal(recoverDocumentIdentity({ ...source, physicalPdfPageNumber: 26 }, 25), null);
  assert.equal(recoverDocumentIdentity(source, 0), null);
});

test("manual page references require physical integer pages", () => {
  assert.throws(() => createOperatorPageReference(document, 1.5), RangeError);
  assert.throws(() => createOperatorPageReference(document, 0), RangeError);
});

test("recovered requirements keep physical page order and stable same-page ordering", () => {
  const existing = [
    { id: "p2", page: 2 },
    { id: "p18-a", page: 18 },
    { id: "p18-b", page: 18 },
    { id: "p20", page: 20 },
    { id: "p22", page: 22 },
  ];

  assert.deepEqual(
    insertRequirementByPhysicalPage(existing, { id: "manual-p18", page: 18 }).map((item) => item.id),
    ["p2", "p18-a", "p18-b", "manual-p18", "p20", "p22"],
  );
  assert.deepEqual(
    insertRequirementByPhysicalPage(existing, { id: "promoted-p20", page: 20 }).map((item) => item.id),
    ["p2", "p18-a", "p18-b", "p20", "promoted-p20", "p22"],
  );
  assert.deepEqual(existing.map((item) => item.id), ["p2", "p18-a", "p18-b", "p20", "p22"]);
});
