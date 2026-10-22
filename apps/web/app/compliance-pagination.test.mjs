import test from "node:test";
import assert from "node:assert/strict";
import { partitionRowsForTemplate } from "./compliance-pagination.ts";

test("partitions response rows into the reference's six page tables without changing order", () => {
  const rows = Array.from({ length: 115 }, (_, index) => `row-${index}`);
  const pages = partitionRowsForTemplate(rows, [18, 28, 20, 23, 20, 6]);

  assert.deepEqual(pages?.map((page) => page.length), [18, 28, 20, 23, 20, 6]);
  assert.deepEqual(pages?.flat(), rows);
  assert.equal(pages?.[0][0], "row-0");
  assert.equal(pages?.[5][5], "row-114");
});

test("uses natural pagination when a template partition does not cover every row", () => {
  assert.equal(partitionRowsForTemplate(["a", "b", "c"], [2, 2]), null);
  assert.equal(partitionRowsForTemplate(["a", "b"], []), null);
});
