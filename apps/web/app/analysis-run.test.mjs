import assert from "node:assert/strict";
import test from "node:test";
import { createAnalysisRun, createWorkUnit, orderWorkUnits, transitionRun, transitionWorkUnit } from "./analysis-run.ts";

const fingerprint = "a".repeat(64);
const at = "2026-11-10T10:00:00.000Z";

test("analysis runs have stable source-bound identities and explicit initial state", () => {
  const first = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt: at, runKey: "upload-1" });
  const retry = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt: at, runKey: "upload-1" });
  assert.deepEqual(first, retry);
  assert.equal(first.status, "queued");
  assert.equal(first.revision, 0);
  assert.notEqual(createAnalysisRun({ sourceFingerprint: fingerprint, createdAt: at, runKey: "upload-2" }).id, first.id);
});

test("run transitions are legal, revisioned, and monotonic", () => {
  const queued = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt: at, runKey: "upload-1" });
  const running = transitionRun(queued, "running", "2026-11-10T10:01:00.000Z");
  const paused = transitionRun(running, "paused", "2026-11-10T10:02:00.000Z");
  assert.equal(paused.revision, 2);
  assert.throws(() => transitionRun(queued, "completed", at), /Illegal analysis run transition/);
  assert.throws(() => transitionRun(running, "failed", at), /monotonic/);
});

test("work-unit identity and ordering ignore source-array and input completion order", () => {
  const make = (sourceIds, ordinal) => createWorkUnit({ runId: "run-1", kind: "inspect", sourceIds, ordinal, createdAt: at });
  const a = make(["page:2", "page:1"], 1);
  const same = make(["page:1", "page:2"], 99);
  const b = make(["page:3"], 0);
  assert.equal(a.idempotencyKey, same.idempotencyKey);
  assert.deepEqual(a.sourceIds, ["page:1", "page:2"]);
  assert.deepEqual(orderWorkUnits([a, b]).map(({ id }) => id), [b.id, a.id]);
  assert.throws(() => orderWorkUnits([a, same]), /Duplicate work-unit/);
});

test("work transitions count attempts only when execution starts", () => {
  const pending = createWorkUnit({ runId: "run-1", kind: "extract", sourceIds: ["page:1"], ordinal: 0, createdAt: at });
  const running = transitionWorkUnit(pending, "running", "2026-11-10T10:01:00.000Z");
  const retryable = transitionWorkUnit(running, "retryable", "2026-11-10T10:02:00.000Z");
  const retry = transitionWorkUnit(retryable, "running", "2026-11-10T10:03:00.000Z");
  assert.equal(running.attempt, 1);
  assert.equal(retryable.attempt, 1);
  assert.equal(retry.attempt, 2);
  assert.equal(transitionWorkUnit(retry, "completed", "2026-11-10T10:04:00.000Z").status, "completed");
  assert.throws(() => transitionWorkUnit(retry, "pending", "2026-11-10T10:04:00.000Z"), /Illegal work-unit transition/);
});

test("run and work-unit constructors reject invalid source identity and timestamps", () => {
  assert.throws(() => createAnalysisRun({ sourceFingerprint: "bad", createdAt: at, runKey: "upload-1" }), /SHA-256/);
  assert.throws(() => createAnalysisRun({ sourceFingerprint: fingerprint, createdAt: "bad", runKey: "upload-1" }), /timestamp/);
  assert.throws(() => createWorkUnit({ runId: "run-1", kind: "inspect", sourceIds: [], ordinal: 0, createdAt: at }), /source IDs/);
  assert.throws(() => createWorkUnit({ runId: "run-1", kind: "inspect", sourceIds: ["page:1", "page:1"], ordinal: 0, createdAt: at }), /source IDs/);
});
