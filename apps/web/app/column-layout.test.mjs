import test from "node:test";
import assert from "node:assert/strict";
import { findColumnLayoutConflict, matchOcrHeaderTokens, normalizeSingleContentColumn, sameColumnLayout, validatePageColumnMap } from "./column-layout.ts";

test("validates a dynamic page schema against literal source headers", () => {
  const headers = ["S. No.", "Equipment", "Parameter", "Minimum", "Unit", "Remarks"];
  const mapped = validatePageColumnMap(headers.map((header, index) => ({
    header,
    role: ["serial", "heading", "heading", "specification", "other", "remark"][index],
  })), headers);
  assert.equal(mapped?.length, 6);
  assert.equal(mapped?.[3].role, "specification");
});

test("rejects invented headers, unknown roles, and malformed page maps", () => {
  assert.equal(validatePageColumnMap([{ header: "OEM Response", role: "response" }], ["Parameter"]), null);
  assert.equal(validatePageColumnMap([{ header: "Unknown", role: "other" }], ["Parameter"]), null);
  assert.equal(validatePageColumnMap("not an array", ["Parameter"]), null);
});

test("allows a layout adapter to verify a literal header inside page text", () => {
  const mapped = validatePageColumnMap(
    [{ header: "Technical Requirement", role: "specification" }],
    [],
    (header) => "Parameter   Technical Requirement   Remarks".includes(header),
  );
  assert.equal(mapped?.[0].header, "Technical Requirement");
  assert.equal(validatePageColumnMap(
    [{ header: "Invented OEM Commitment", role: "compliance" }],
    [],
    () => false,
  ), null);
});

test("accepts only identical header and role layouts for a shared response sheet", () => {
  const base = [
    { header: "Specification", role: "heading" },
    { header: "Description", role: "specification" },
  ];
  assert.equal(sameColumnLayout(base, [...base]), true);
  assert.equal(sameColumnLayout(base, [{ ...base[0] }, { header: "Requirement", role: "specification" }]), false);
  assert.equal(sameColumnLayout(base, [{ ...base[0] }, { ...base[1], role: "remark" }]), false);
  assert.equal(sameColumnLayout(base, [...base, { header: "Quantity", role: "quantity" }]), false);
});

test("identifies the page requiring review before incompatible layouts are combined", () => {
  const first = [
    { header: "Parameter", role: "heading" },
    { header: "Specification", role: "specification" },
  ];
  const alternate = [
    { header: "Item", role: "heading" },
    { header: "Requirement", role: "specification" },
    { header: "Unit", role: "other" },
  ];
  assert.equal(findColumnLayoutConflict(first, [
    { page: 4, columns: first },
    { page: 9, columns: alternate },
  ]), 9);
  assert.equal(findColumnLayoutConflict(first, [
    { page: 4, columns: first },
    { page: 9, columns: [], invalid: true },
  ]), 9);
  assert.equal(findColumnLayoutConflict(first, [
    { page: 4, columns: first },
    { page: 5, columns: [] },
  ]), undefined);
});


test('one technical content column remains a specification when its header was classified as a parameter heading',()=>{
 const columns=[{header:'Technical Parameters NIQ',role:'heading'},{header:'Remark',role:'remark'},{header:'Compliance Y/N',role:'compliance'}];
 const before=structuredClone(columns);const normalized=normalizeSingleContentColumn(columns);
 assert.equal(normalized[0].role,'specification');assert.equal(normalized[0].header,'Technical Parameters NIQ');assert.deepEqual(columns,before);
 assert.deepEqual(normalized.slice(1),columns.slice(1));
 assert.equal(normalizeSingleContentColumn([{header:'Item',role:'heading'},{header:'Description',role:'other'}])[0].role,'heading');
 const split=[{header:'Parameter',role:'heading'},{header:'Required value',role:'specification'}];
 assert.deepEqual(normalizeSingleContentColumn(split),split);
});


test('literal header verification and layout identity preserve scientific unit case',()=>{
 assert.equal(validatePageColumnMap([{header:'Power (MW)',role:'specification'}],['Power (mW)']),null);
 assert.equal(sameColumnLayout([{header:'Power (mW)',role:'specification'}],[{header:'Power (MW)',role:'specification'}]),false);
});

test('matchOcrHeaderTokens verifies OCR table headers across noisy transcripts and interleaved lines', () => {
  const ocrPageText = `
    SIL. Item Description Compliance
    No. (Yes/No)
    1. Floor standing X-Band EPR Spectrometer System
  `;
  assert.equal(matchOcrHeaderTokens("Sl. No.", ocrPageText), true);
  assert.equal(matchOcrHeaderTokens("Item Description", ocrPageText), true);
  assert.equal(matchOcrHeaderTokens("Compliance (Yes/No)", ocrPageText), true);
  assert.equal(matchOcrHeaderTokens("Invented Vendor Header", ocrPageText), false);
  assert.equal(matchOcrHeaderTokens("", ocrPageText), false);
  assert.equal(matchOcrHeaderTokens("Sl. No.", ""), false);
});
