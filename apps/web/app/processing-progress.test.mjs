import assert from "node:assert/strict";
import test from "node:test";
import { PROCESSING_STEPS, formatElapsedSeconds, processingStepIndex } from "./processing-progress.ts";

test("progress indicators follow the extraction stages in actual execution order", () => {
  assert.deepEqual(PROCESSING_STEPS.map((step) => step.id), ["reading", "locating", "mapping", "extracting", "verifying"]);
  assert.equal(processingStepIndex("reading"), 0);
  assert.equal(processingStepIndex("mapping"), 2);
  assert.equal(processingStepIndex("verifying"), 4);
  assert.equal(processingStepIndex("complete"), 5);
});

test("terminal failures and cancellations do not appear as a running step", () => {
  assert.equal(processingStepIndex("error"), -1);
  assert.equal(processingStepIndex("cancelled"), -1);
});

test("formats elapsed processing time without inventing a percentage", () => {
  assert.equal(formatElapsedSeconds(0), "0s");
  assert.equal(formatElapsedSeconds(59.9), "59s");
  assert.equal(formatElapsedSeconds(61), "1:01");
  assert.equal(formatElapsedSeconds(-4), "0s");
});
