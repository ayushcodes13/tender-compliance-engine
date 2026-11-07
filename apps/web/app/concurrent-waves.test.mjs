import test from "node:test";
import assert from "node:assert/strict";
import { mapInConcurrentWaves } from "./concurrent-waves.ts";

test("runs work in bounded waves, preserves input order, and reports completed counts", async () => {
  const values = [5, 4, 3, 2, 1];
  const progress = [];
  let active = 0;
  let maximumActive = 0;
  const result = await mapInConcurrentWaves(values, 2, async (value) => {
    active += 1;
    maximumActive = Math.max(maximumActive, active);
    await new Promise((resolve) => setTimeout(resolve, value % 2));
    active -= 1;
    return value * 2;
  }, (completed, total) => progress.push([completed, total]));

  assert.deepEqual(result, [10, 8, 6, 4, 2]);
  assert.equal(maximumActive, 2);
  assert.deepEqual(progress, [[2, 5], [4, 5], [5, 5]]);
});

test("rejects invalid concurrency and supports empty work", async () => {
  await assert.rejects(mapInConcurrentWaves([], 0, async () => null), /positive integer/);
  assert.deepEqual(await mapInConcurrentWaves([], 3, async () => null), []);
});
