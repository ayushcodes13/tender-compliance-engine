import test from "node:test";
import assert from "node:assert/strict";
import { groupVisualPages, validateVisualPageBatchResponse } from "./visual-page-batching.ts";

test("groups visual pages into bounded batches without reordering", () => {
  assert.deepEqual(groupVisualPages([1, 2, 3, 4, 5]), [[1, 2], [3, 4], [5]]);
  assert.deepEqual(groupVisualPages([]), []);
  assert.throws(() => groupVisualPages([1], 0), /positive integer/);
});

test("validates page-local columns and region-indexed candidates and binds candidates to their parent page", () => {
  const result = validateVisualPageBatchResponse({ page_results: [
    { page: 3, columns: [{ header: "Specification", role: "specification" }], requirements: [{ quote: "Pump shall deliver 200 bar.", visual_region_index: 1 }] },
    { page: 4, columns: [], requirements: [] },
  ] }, [3, 4], { requireColumns: true });
  assert.equal(result.ok, true);
  if (result.ok) {
    assert.deepEqual(result.pages.map((page) => page.page), [3, 4]);
    assert.equal(result.pages[0].requirements[0].page, 3);
    assert.equal(result.pages[0].requirements[0].visual_region_index, 1);
    assert.deepEqual(result.pages[1].columns, []);
  }
});

test("rejects missing, duplicate, out-of-batch, or invalid-region page results", () => {
  const valid = (page) => ({ page, columns: [], requirements: [] });
  for (const pageResults of [
    [valid(1)],
    [valid(1), valid(1)],
    [valid(1), valid(3)],
    [{ page: 1, columns: [], requirements: [{ visual_region_index: 3 }] }, valid(2)],
  ]) assert.equal(validateVisualPageBatchResponse({ page_results: pageResults }, [1, 2], { requireColumns: true }).ok, false);
});
