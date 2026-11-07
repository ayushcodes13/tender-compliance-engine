import test from "node:test";
import assert from "node:assert/strict";
import { mapWithConcurrency, mapWithConcurrencySettled } from "./concurrent-map.ts";

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

test("settles all bounded work and preserves fulfilled batch results beside a timeout", async () => {
  let active = 0;
  let peak = 0;
  const settledIndexes = [];
  const results = await mapWithConcurrencySettled(["parsed-a", "timeout", "parsed-b"], 2, async (item) => {
    active += 1;
    peak = Math.max(peak, active);
    await new Promise((resolve) => setTimeout(resolve, item === "timeout" ? 5 : 1));
    active -= 1;
    if (item === "timeout") throw new DOMException("provider deadline", "TimeoutError");
    return item;
  }, (_completed, _total, _settled, index) => { settledIndexes.push(index); });
  assert.deepEqual([...settledIndexes].sort((x, y) => x - y), [0, 1, 2]);
  assert.deepEqual(results.map((result) => result.status), ["fulfilled", "rejected", "fulfilled"]);
  assert.deepEqual(results.filter((result) => result.status === "fulfilled").map((result) => result.value), ["parsed-a", "parsed-b"]);
  assert.equal(results[1].reason.name, "TimeoutError");
  assert.equal(peak, 2);
});

test("settles caller cancellation without discarding another completed item", async () => {
  const controller = new AbortController();
  const results = await mapWithConcurrencySettled([1, 2], 2, async (item) => {
    if (item === 1) return "completed";
    controller.abort(new DOMException("cancelled", "AbortError"));
    throw controller.signal.reason;
  });
  assert.deepEqual(results.map((result) => result.status), ["fulfilled", "rejected"]);
  assert.equal(results[0].value, "completed");
  assert.equal(results[1].reason.name, "AbortError");
});
