import test from "node:test";
import assert from "node:assert/strict";
import { shouldUseStructuredTableExtraction } from "./extraction-route.ts";

test("uses visual interpretation when structured and visual table evidence and credentials exist", () => {
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: true,
    hasVisualPages: true,
    hasModelCredentials: true,
  }), false);
});

test("keeps structured extraction as fallback when visual interpretation is unavailable", () => {
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
