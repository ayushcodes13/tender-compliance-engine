import test from "node:test";
import assert from "node:assert/strict";
import { shouldUseStructuredTableExtraction, technicalRoutingPages } from "./extraction-route.ts";

test("configured local or hosted models route pages before a structured-table shortcut", () => {
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: true,
    hasVisualPages: true,
    hasConfiguredModel: true,
  }), false);
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: true,
    hasVisualPages: false,
    hasConfiguredModel: true,
  }), false);
});

test("recognized source-cell geometry remains the deterministic offline fallback", () => {
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: true,
    hasVisualPages: true,
    hasConfiguredModel: false,
  }), true);
  assert.equal(shouldUseStructuredTableExtraction({
    hasStructuredPages: false,
    hasVisualPages: true,
    hasConfiguredModel: false,
  }), false);
});

test("page routing includes bordered and borderless technical sections, not just vector tables", () => {
  const pages = [
    { page: 1, text: "Cover and contents", hasVectorTableGeometry: false },
    { page: 2, text: "Technical requirements: resolution 1 micrometre", hasVectorTableGeometry: false },
    { page: 3, text: "Specification | Compliance", hasVectorTableGeometry: true },
    { page: 4, text: "    ", hasVectorTableGeometry: false },
  ];
  assert.deepEqual(technicalRoutingPages(pages).map((page) => page.page), [1, 2, 3]);
});
