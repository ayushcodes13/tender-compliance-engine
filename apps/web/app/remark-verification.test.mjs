import test from "node:test";
import assert from "node:assert/strict";
import { retainVerifiedRemark } from "./remark-verification.ts";

test("retains an independently verified remark without changing its words", () => {
  assert.deepEqual(retainVerifiedRemark({
    remark: "  Protection grade IP67  ",
    requiresSourceLocation: true,
    hasSourceLocation: true,
  }), { remark: "Protection grade IP67", omittedUnverified: false });
});

test("drops only the unlocated remark, not the independently verified requirement", () => {
  const result = retainVerifiedRemark({
    remark: "Claimed model-only deviation: +20%",
    requiresSourceLocation: true,
    hasSourceLocation: false,
  });
  assert.deepEqual(result, { remark: "", omittedUnverified: true });
});

test("an empty optional remark is not treated as a model hallucination", () => {
  assert.deepEqual(retainVerifiedRemark({
    remark: "  ", requiresSourceLocation: true, hasSourceLocation: false,
  }), { remark: "", omittedUnverified: false });
});

test("preserves existing general-extraction remark behavior outside compliance-sheet verification", () => {
  assert.deepEqual(retainVerifiedRemark({
    remark: "Native page note", requiresSourceLocation: false, hasSourceLocation: false,
  }), { remark: "Native page note", omittedUnverified: false });
});
