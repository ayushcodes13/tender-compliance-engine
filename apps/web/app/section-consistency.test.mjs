import test from "node:test";
import assert from "node:assert/strict";
import { validatePossibleSourceConflicts } from "./section-consistency.ts";

const pages = new Map([
  [1, "Technical specifications for X-Band EPR spectrometer system"],
  [5, "Techno-Commercial Compliance Sheet for an advanced Spectrofluorometer equipped with modular facilities"],
]);

test("reports a possible cross-section conflict only with exact source quotes on both pages", () => {
  const result = validatePossibleSourceConflicts([{
    page_a: 1,
    quote_a: "X-Band EPR spectrometer system",
    page_b: 5,
    quote_b: "advanced Spectrofluorometer equipped with modular facilities",
    reason: "The technical subject named in the compliance schedule differs from the equipment identified in the specification title.",
  }], pages);

  assert.deepEqual(result.uncertainPages, [1, 5]);
  assert.deepEqual(result.routedPages, [1, 5]);
  assert.equal(result.rejectedCount, 0);
  assert.equal(result.warnings.length, 1);
  assert.match(result.warnings[0], /Possible cross-section inconsistency/);
  assert.match(result.warnings[0], /neither source is treated as authoritative/);
});

test("rejects unsupported quotes while leaving the cited source pages uncertain", () => {
  const result = validatePossibleSourceConflicts([{
    page_a: 1,
    quote_a: "X-Band EPR spectrometer system",
    page_b: 5,
    quote_b: "advanced EPR spectrometer equipped with modular facilities",
    reason: "The title is different.",
  }], pages);

  assert.deepEqual(result.uncertainPages, [1, 5]);
  assert.deepEqual(result.routedPages, []);
  assert.equal(result.rejectedCount, 1);
  assert.deepEqual(result.warnings, []);
});

test("rejects invalid page pairs and unbounded conflict content", () => {
  const result = validatePossibleSourceConflicts([
    { page_a: 1, quote_a: "X-Band EPR spectrometer system", page_b: 1, quote_b: "X-Band EPR spectrometer system", reason: "same page" },
    { page_a: 1, quote_a: "x".repeat(501), page_b: 5, quote_b: "advanced Spectrofluorometer equipped with modular facilities", reason: "different" },
  ], pages);

  assert.deepEqual(result.uncertainPages, [1, 5]);
  assert.deepEqual(result.routedPages, []);
  assert.equal(result.rejectedCount, 2);
  assert.deepEqual(result.warnings, []);
});

test("source-bound Saha title discrepancy remains an unresolved two-page review item", () => {
  const sourcePages = new Map([
    [1, "Supply of “Floor standing X-Band EPR Spectrometer System” at SINP"],
    [5, "Techno-Commercial Compliance Sheet For “An advanced Spectrofluorometer equipped with modular facilities capable of monitoring chiral fluorescence” NIT No. GTE/X-Band EPR Spectrometer System"],
  ]);
  const result = validatePossibleSourceConflicts([{
    page_a: 1,
    quote_a: "Supply of “Floor standing X-Band EPR Spectrometer System” at SINP",
    page_b: 5,
    quote_b: "“An advanced Spectrofluorometer equipped with modular facilities capable of monitoring chiral fluorescence”",
    reason: "The Annexure II title names a different equipment subject from the tender title and its own NIT number.",
  }], sourcePages);

  assert.deepEqual(result.uncertainPages, [1, 5]);
  assert.deepEqual(result.routedPages, [1, 5]);
  assert.equal(result.rejectedCount, 0);
  assert.match(result.warnings[0], /neither source is treated as authoritative/);
});
