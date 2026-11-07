import test from "node:test";
import assert from "node:assert/strict";
import {
  batchTextPagesForAudit,
  TEXT_PAGE_AUDIT_MAX_BATCHES,
  TEXT_PAGE_AUDIT_MAX_CHARS,
  TEXT_PAGE_AUDIT_MAX_PAGES,
  TEXT_PAGE_AUDIT_TARGET_CHARS,
} from "./text-page-audit.ts";

test("batches text audit pages by size and page count without dropping ordinary inputs", () => {
  const pages = Array.from({ length: 9 }, (_, index) => ({ page: index + 1, text: "x".repeat(10_000), knownRows: [] }));
  const result = batchTextPagesForAudit(pages);
  assert.equal(result.oversizedPages.length, 0);
  assert.equal(result.deferredPages.length, 0);
  assert.deepEqual(result.batches.flatMap((batch) => batch.pages.map((page) => page.page)), pages.map((page) => page.page));
  assert.ok(result.batches.every((batch) => batch.pages.length <= TEXT_PAGE_AUDIT_MAX_PAGES));
  assert.ok(result.batches.every((batch) => batch.estimatedChars <= TEXT_PAGE_AUDIT_TARGET_CHARS));
});

test("gives a large but bounded page its own audit batch", () => {
  const largePage = { page: 1, text: "x".repeat(TEXT_PAGE_AUDIT_TARGET_CHARS + 1), knownRows: [] };
  const result = batchTextPagesForAudit([largePage, { page: 2, text: "small", knownRows: [] }]);
  assert.equal(result.batches.length, 2);
  assert.deepEqual(result.batches.map((batch) => batch.pages.map((page) => page.page)), [[1], [2]]);
  assert.equal(result.oversizedPages.length, 0);
});

test("reports pages over the hard request cap and batches beyond the analysis budget as unresolved", () => {
  const pages = Array.from({ length: (TEXT_PAGE_AUDIT_MAX_BATCHES + 1) * TEXT_PAGE_AUDIT_MAX_PAGES }, (_, index) => ({
    page: index + 1,
    text: "x".repeat(Math.floor(TEXT_PAGE_AUDIT_TARGET_CHARS / TEXT_PAGE_AUDIT_MAX_PAGES) - 40),
    knownRows: [],
  }));
  pages.push({ page: 999, text: "x".repeat(TEXT_PAGE_AUDIT_MAX_CHARS + 1), knownRows: [] });
  const result = batchTextPagesForAudit(pages);
  assert.equal(result.batches.length, TEXT_PAGE_AUDIT_MAX_BATCHES);
  assert.ok(result.deferredPages.length > 0);
  assert.deepEqual(result.oversizedPages, [999]);
  assert.equal(new Set(result.batches.flatMap((batch) => batch.pages.map((page) => page.page))).size, TEXT_PAGE_AUDIT_MAX_BATCHES * TEXT_PAGE_AUDIT_MAX_PAGES);
});
