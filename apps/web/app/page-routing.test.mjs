import test from "node:test";
import assert from "node:assert/strict";
import { buildRoutingBatches, expandRoutedSections, ROUTING_BATCH_CHARACTER_LIMIT } from "./page-routing.ts";

test("summarizes every text-bearing page with technical signals and preserves page identity", () => {
  const batches = buildRoutingBatches([
    { page: 1, text: "Tender cover and bidder details" },
    { page: 2, text: "Technical Specifications\nUniversal Testing Machine\nCapacity: 300 kN" },
    { page: 3, text: "Annexure II\nTechnical Compliance Schedule\nAccuracy: ±0.1 mm" },
    { page: 4, text: "   " },
  ]);
  const represented = batches.flatMap((batch) => batch.pages.map((page) => page.page));
  assert.deepEqual(represented.sort((a, b) => a - b), [1, 2, 3]);
  assert.match(batches.flatMap((batch) => batch.input).join("\n"), /300 kN/);
  assert.match(batches.flatMap((batch) => batch.input).join("\n"), /±0\.1 mm/);
});

test("splits long tenders into bounded routing batches with one-page overlap", () => {
  const pages = Array.from({ length: 42 }, (_, index) => ({
    page: index + 1,
    text: `Page ${index + 1}\nTechnical parameter ${index + 1}\nRated capacity ${index + 10} kN`,
    hasVectorTableGeometry: index % 2 === 0,
  }));
  const batches = buildRoutingBatches(pages, 2_000);
  assert.ok(batches.length > 1);
  assert.ok(batches.every((batch) => batch.input.length <= 2_000));
  assert.deepEqual(batches[0].pages.at(-1)?.page, batches[1].pages[0].page);
  const uniquePages = [...new Set(batches.flatMap((batch) => batch.pages.map((page) => page.page)))];
  assert.deepEqual(uniquePages, pages.map((page) => page.page));
  assert.equal(ROUTING_BATCH_CHARACTER_LIMIT, 10_000);
});

test("records pages whose source text was clipped to a bounded excerpt", () => {
  const longText = [
    "Cover paragraph",
    ...Array.from({ length: 80 }, (_, index) => `Requirement ${index + 1}: rated pressure must be at least ${index + 10} MPa`),
  ].join("\n");
  const [batch] = buildRoutingBatches([{ page: 7, text: longText }]);
  assert.deepEqual(batch.clippedPages, [7]);
  assert.ok(batch.input.length < longText.length);
});

test("expands model-proposed section ranges only to known source pages", () => {
  const selected = expandRoutedSections([
    { title: "Specifications", start_page: 4, end_page: 7, section_type: "technical_requirements", reason: "Equipment parameters" },
    { title: "Response schedule", start_page: 10, end_page: 12, section_type: "compliance_schedule", reason: "Bidder response fields" },
  ], [1, 4, 5, 7, 10, 11, 13]);
  assert.deepEqual(selected, [4, 5, 7, 10, 11]);
});
