import test from "node:test";
import assert from "node:assert/strict";
import { mapWithConcurrency } from "./concurrent-map.ts";

test("starts the next independent item when any worker finishes and preserves result order", async () => {
  const items = ["slow", "fast", "middle", "next"];
  const started = [];
  const pending = new Map();
  const progress = [];
  const resultPromise = mapWithConcurrency(items, 3, async (item, index) => {
    started.push(item);
    await new Promise((resolve) => pending.set(item, resolve));
    return `${index}:${item}`;
  }, (completed, total) => progress.push([completed, total]));

  while (started.length < 3) await new Promise((resolve) => setImmediate(resolve));
  pending.get("fast")();
  while (!started.includes("next")) await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(started, ["slow", "fast", "middle", "next"]);

  pending.get("middle")();
  pending.get("next")();
  pending.get("slow")();
  assert.deepEqual(await resultPromise, ["0:slow", "1:fast", "2:middle", "3:next"]);
  assert.deepEqual(progress.at(-1), [4, 4]);
});

test("rejects invalid concurrency and supports empty work", async () => {
  await assert.rejects(mapWithConcurrency([], 0, async () => null), /positive integer/);
  assert.deepEqual(await mapWithConcurrency([], 3, async () => null), []);
});
