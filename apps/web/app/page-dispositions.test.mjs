import test from "node:test";
import assert from "node:assert/strict";
import { validatePageDispositions } from "./page-dispositions.ts";

test("validates page-specific route classes and leaves omitted pages unresolved", () => {
  const result = validatePageDispositions([
    { page: 1, classification: "relevant", reason: "Technical parameters are visible." },
    { page: 2, classification: "possibly_relevant", reason: "The excerpt is clipped." },
  ], [1, 2, 3]);
  assert.equal(result.ok, true);
  assert.deepEqual(result.dispositions.map(({ classification }) => classification), ["relevant", "possibly_relevant"]);
  assert.deepEqual(result.unresolvedPages, [3]);
});

test("rejects duplicate, out-of-group, or reasonless page exclusions", () => {
  assert.equal(validatePageDispositions([
    { page: 1, classification: "excluded", reason: "Only commercial content." },
    { page: 1, classification: "relevant", reason: "Specification text." },
  ], [1]).ok, false);
  assert.equal(validatePageDispositions([
    { page: 2, classification: "excluded", reason: "Only commercial content." },
  ], [1]).ok, false);
  assert.equal(validatePageDispositions([
    { page: 1, classification: "excluded", reason: " " },
  ], [1]).ok, false);
});
