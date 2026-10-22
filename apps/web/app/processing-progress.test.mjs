import assert from "node:assert/strict";
import test from "node:test";
import { PROCESSING_STEPS, processingStepIndex } from "./processing-progress.ts";

test("progress indicators follow the extraction stages in actual execution order", () => {
  assert.deepEqual(PROCESSING_STEPS.map((step) => step.id), ["reading", "locating", "mapping", "extracting", "verifying"]);
  assert.equal(processingStepIndex("reading"), 0);
  assert.equal(processingStepIndex("mapping"), 2);
  assert.equal(processingStepIndex("verifying"), 4);
  assert.equal(processingStepIndex("complete"), 5);
});
