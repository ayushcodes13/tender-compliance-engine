import test from "node:test";
import assert from "node:assert/strict";
import { shouldUseStructuredTableExtraction } from "./extraction-route.ts";

test("prefers exact source-cell geometry when a recognized technical table exists", () => {
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: true,
    hasVisualPages: true,
    hasModelCredentials: true,
  }), true);
});

test("uses structured extraction without requiring a visual renderer or model credential", () => {
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: true,
    hasVisualPages: false,
    hasModelCredentials: true,
  }), true);
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: true,
    hasVisualPages: true,
    hasModelCredentials: false,
  }), true);
});

test("does not select structured extraction when no structured table exists", () => {
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: false,
    hasVisualPages: true,
    hasModelCredentials: true,
  }), false);
});
