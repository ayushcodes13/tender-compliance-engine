import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { createAnalysisRun, createWorkUnit, executeWorkUnit, transitionRun, transitionWorkUnit } from "./analysis-run.ts";
import { appendPlanningRound, createEncryptedSQLiteRunStore, createLocalRunStoreFromEnvironment, latestPlanningRound, updateRunFinalResult, updateRunState, updateRunWorkUnit } from "./run-store.ts";

const fingerprint = "c".repeat(64);
const keyHex = "ab".repeat(32);
const createdAt = "2026-11-10T10:00:00.000Z";
const storeModule = fileURLToPath(new URL("./run-store.ts", import.meta.url));

function makeSnapshot() {
  const run = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "restart-test" });
  const unit = createWorkUnit({ runId: run.id, kind: "extract", sourceIds: ["doc:page:1:table:1"], ordinal: 0, createdAt, operationKey: "table" });
  return {
    schemaVersion: 1,
    run,
    plan: null,
    planningRounds: [],
    workUnits: [unit],
    artifacts: [{ workUnitId: unit.id, value: { text: "CONFIDENTIAL_TEST_REQUIREMENT_731" } }],
  };
}

function makePlan(run, decision = "continue") {
  return {
    schemaVersion: 1,
    runId: run.id,
    sourceFingerprint: run.sourceFingerprint,
    proposal: {
      decision,
      decisionRationale: `The planner selected ${decision}.`,
      task: "Prepare a technical response matrix.",
      scope: [],
      sections: [],
      actions: [],
      openQuestions: [],
    },
  };
}

test("planning rounds append in sequence and keep the compatibility alias at the latest decision", () => {
  const run = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "planning-rounds" });
  let snapshot = { schemaVersion: 1, run, plan: null, planningRounds: [], workUnits: [], artifacts: [] };
  const firstPlan = makePlan(run);
  snapshot = appendPlanningRound(snapshot, {
    inputFingerprint: "d".repeat(64), plan: firstPlan, outcomes: [], createdAt,
  });
  assert.equal(latestPlanningRound(snapshot).roundIndex, 0);
  assert.equal(snapshot.plan, firstPlan);

  const secondPlan = makePlan(run, "needs_review");
  snapshot = appendPlanningRound(snapshot, {
    inputFingerprint: "e".repeat(64), plan: secondPlan,
    outcomes: [{ sourceId: "doc:page:1:image:1", status: "executed", summary: "Visual region inspected; wording needs review." }],
    createdAt: "2026-11-10T10:01:00.000Z",
  });
  assert.deepEqual(snapshot.planningRounds.map((round) => round.roundIndex), [0, 1]);
  assert.equal(latestPlanningRound(snapshot).decision, "needs_review");
  assert.equal(snapshot.plan, secondPlan);
});

test("planning round validation rejects mismatched decision and duplicate outcome sources", () => {
  const run = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "invalid-round" });
  const base = { schemaVersion: 1, run, plan: null, planningRounds: [], workUnits: [], artifacts: [] };
  const plan = makePlan(run);
  const validRound = appendPlanningRound(base, { inputFingerprint: "d".repeat(64), plan, outcomes: [], createdAt });
  assert.throws(() => updateRunState({
    ...validRound,
    planningRounds: [{ ...validRound.planningRounds[0], decision: "stop" }],
  }, run), /invalid planning round/);
  assert.throws(() => appendPlanningRound(base, {
    inputFingerprint: "d".repeat(64), plan, outcomes: [
      { sourceId: "doc:page:1", status: "executed", summary: "Done." },
      { sourceId: "doc:page:1", status: "failed", summary: "Failed." },
    ], createdAt,
  }), /invalid planning outcome/);
});

test("opening a legacy one-shot plan migrates it to a review-safe round zero", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tce-run-store-round-migration-"));
  const databasePath = join(directory, "runs.sqlite");
  try {
    const run = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "legacy-plan" });
    const legacyPlan = {
      schemaVersion: 1,
      runId: run.id,
      sourceFingerprint: run.sourceFingerprint,
      proposal: { task: "Prepare a matrix", scope: [], sections: [], actions: [], openQuestions: [] },
    };
    const store = createEncryptedSQLiteRunStore({ databasePath, keyHex });
    store.save({ schemaVersion: 1, run, plan: legacyPlan, workUnits: [], artifacts: [] });
    const restored = store.load(run.id);
    assert.equal(restored.planningRounds.length, 1);
    assert.equal(restored.planningRounds[0].roundIndex, 0);
    assert.equal(restored.planningRounds[0].decision, "needs_review");
    assert.match(restored.plan.proposal.decisionRationale, /Legacy one-shot plan migrated/);
    assert.equal(latestPlanningRound(restored), restored.planningRounds[0]);
    store.close();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("encrypted SQLite snapshots survive reopening from a fresh Node process", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tce-run-store-"));
  const databasePath = join(directory, "runs.sqlite");
  try {
    const snapshot = makeSnapshot();
    const store = createEncryptedSQLiteRunStore({ databasePath, keyHex });
    store.save(snapshot);
    store.close();
    const databaseBytes = await readFile(databasePath);
    assert.equal(databaseBytes.includes(Buffer.from("CONFIDENTIAL_TEST_REQUIREMENT_731")), false);

    const script = `
      import { createEncryptedSQLiteRunStore } from ${JSON.stringify(pathToFileURL(storeModule).href)};
      const store = createEncryptedSQLiteRunStore({ databasePath: process.env.TCE_TEST_DB, keyHex: process.env.TCE_TEST_KEY });
      const snapshot = store.load(process.env.TCE_TEST_RUN);
      console.log(snapshot?.artifacts?.[0]?.value?.text ?? "missing");
      store.close();
    `;
    const child = spawnSync(process.execPath, ["--experimental-strip-types", "--input-type=module", "-e", script], {
      encoding: "utf8",
      env: { ...process.env, TCE_TEST_DB: databasePath, TCE_TEST_KEY: keyHex, TCE_TEST_RUN: snapshot.run.id },
    });
    assert.equal(child.status, 0, child.stderr);
    assert.match(child.stdout, /CONFIDENTIAL_TEST_REQUIREMENT_731/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("authenticated encryption rejects a wrong key and tampered ciphertext", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tce-run-store-auth-"));
  const databasePath = join(directory, "runs.sqlite");
  try {
    const snapshot = makeSnapshot();
    const store = createEncryptedSQLiteRunStore({ databasePath, keyHex });
    store.save(snapshot);
    store.close();
    const wrongKeyStore = createEncryptedSQLiteRunStore({ databasePath, keyHex: "cd".repeat(32) });
    assert.throws(() => wrongKeyStore.load(snapshot.run.id), /could not be authenticated/);
    wrongKeyStore.close();

    const database = new DatabaseSync(databasePath);
    database.exec("PRAGMA wal_checkpoint(TRUNCATE);");
    const row = database.prepare("SELECT ciphertext_and_tag FROM analysis_runs WHERE run_id = ?").get(snapshot.run.id);
    const changed = Buffer.from(row.ciphertext_and_tag);
    changed[0] ^= 1;
    database.prepare("UPDATE analysis_runs SET ciphertext_and_tag = ? WHERE run_id = ?").run(changed, snapshot.run.id);
    database.close();
    const tamperedStore = createEncryptedSQLiteRunStore({ databasePath, keyHex });
    assert.throws(() => tamperedStore.load(snapshot.run.id), /could not be authenticated/);
    tamperedStore.close();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("completed model work and final analysis are checkpointed as one resumable snapshot", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tce-run-store-checkpoint-"));
  const databasePath = join(directory, "runs.sqlite");
  try {
    const run = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "checkpoint-test" });
    let snapshot = { schemaVersion: 1, run: transitionRun(run, "running", createdAt), plan: null, workUnits: [], artifacts: [] };
    const store = createEncryptedSQLiteRunStore({ databasePath, keyHex });
    store.save(snapshot);
    const unit = createWorkUnit({ runId: run.id, kind: "inspect", sourceIds: ["doc:page:1"], ordinal: 0, createdAt, operationKey: "page_routing" });
    const execution = await executeWorkUnit({
      unit,
      execute: async () => ({ sections: [{ title: "Technical requirements", pages: [1] }] }),
      isSuccessful: (result) => Array.isArray(result.sections),
      now: () => createdAt,
      onState: (current) => { snapshot = updateRunWorkUnit(snapshot, current); store.save(snapshot); },
      onResult: (current, result) => { snapshot = updateRunWorkUnit(snapshot, current, result); store.save(snapshot); },
    });
    assert.equal(execution.unit.status, "completed");
    assert.deepEqual(store.load(run.id).artifacts[0].value, { sections: [{ title: "Technical requirements", pages: [1] }] });
    const analysis = { document: { documentFingerprint: fingerprint }, requirements: [], completionStatus: "complete" };
    snapshot = updateRunFinalResult(snapshot, transitionRun(snapshot.run, "completed", createdAt), analysis);
    store.save(snapshot);
    store.close();

    const reopened = createEncryptedSQLiteRunStore({ databasePath, keyHex });
    const restored = reopened.load(run.id);
    assert.equal(restored.run.status, "completed");
    assert.equal(restored.workUnits[0].status, "completed");
    assert.deepEqual(restored.finalResult, analysis);
    reopened.close();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("paused runs persist a partial result and clear it when work resumes", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tce-run-store-partial-checkpoint-"));
  const databasePath = join(directory, "runs.sqlite");
  try {
    const run = createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "partial-checkpoint-test" });
    const store = createEncryptedSQLiteRunStore({ databasePath, keyHex });
    const running = transitionRun(run, "running", createdAt);
    const initial = { schemaVersion: 1, run: running, plan: null, workUnits: [], artifacts: [] };
    store.save(initial);
    const partial = { document: { documentFingerprint: fingerprint }, requirements: [], completionStatus: "partial" };
    const paused = transitionRun(running, "paused", createdAt);
    const snapshot = updateRunFinalResult(initial, paused, partial);
    store.save(snapshot);
    assert.equal(store.load(run.id).run.status, "paused");
    assert.deepEqual(store.load(run.id).finalResult, partial);

    const resumed = transitionRun(paused, "running", createdAt);
    const resumedSnapshot = updateRunState({ ...snapshot, finalResult: undefined }, resumed);
    store.save(resumedSnapshot);
    assert.equal(store.load(run.id).run.status, "running");
    assert.equal(store.load(run.id).finalResult, undefined, "The old partial result is cleared before work resumes");
    store.close();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("completed native-text extraction work cannot be stored without its result artifact", () => {
  const run = transitionRun(createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "native-text-artifact" }), "running", createdAt);
  const snapshot = { schemaVersion: 1, run, plan: null, workUnits: [], artifacts: [] };
  const pending = createWorkUnit({ runId: run.id, kind: "extract", sourceIds: ["doc:page:1"], ordinal: 0, createdAt, operationKey: "general_requirement_extraction" });
  const running = transitionWorkUnit(pending, "running", createdAt);
  const completed = transitionWorkUnit(running, "completed", createdAt);

  assert.throws(() => updateRunWorkUnit(snapshot, completed), /must have a persisted result artifact/);
  const persisted = updateRunWorkUnit(snapshot, completed, { ok: true, parsed: { requirements: [] }, allowedPages: [1] });
  assert.equal(persisted.workUnits[0].status, "completed");
  assert.deepEqual(persisted.artifacts[0], { workUnitId: completed.id, value: { ok: true, parsed: { requirements: [] }, allowedPages: [1] } });
});

test("completed planner table work cannot be stored without its classification artifact", () => {
  const run = transitionRun(createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "planner-table-artifact" }), "running", createdAt);
  const snapshot = { schemaVersion: 1, run, plan: null, workUnits: [], artifacts: [] };
  const pending = createWorkUnit({ runId: run.id, kind: "inspect", sourceIds: ["doc:page:1:table:vector:1"], ordinal: 0, createdAt, operationKey: "table" });
  const running = transitionWorkUnit(pending, "running", createdAt);
  const completed = transitionWorkUnit(running, "completed", createdAt);

  assert.throws(() => updateRunWorkUnit(snapshot, completed), /must have a persisted result artifact/);
  const classification = { modelInspectionComplete: true, rowLabels: [{ row_index: 0, row_type: "requirement" }] };
  const persisted = updateRunWorkUnit(snapshot, completed, classification);
  assert.equal(persisted.workUnits[0].status, "completed");
  assert.deepEqual(persisted.artifacts[0], { workUnitId: completed.id, value: classification });
});

test("completed planner OCR extraction work cannot be stored without its result artifact", () => {
  const run = transitionRun(createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "planner-ocr-artifact" }), "running", createdAt);
  const snapshot = { schemaVersion: 1, run, plan: null, workUnits: [], artifacts: [] };
  const pending = createWorkUnit({ runId: run.id, kind: "extract", sourceIds: ["doc:page:2:ocr:1"], ordinal: 0, createdAt, operationKey: "planned_ocr_extraction:action" });
  const running = transitionWorkUnit(pending, "running", createdAt);
  const completed = transitionWorkUnit(running, "completed", createdAt);

  assert.throws(() => updateRunWorkUnit(snapshot, completed), /must have a persisted result artifact/);
  const result = { ok: true, parsed: { requirements: [{ page: 2, quote: "Pressure shall remain below 2 Pa." }] }, allowedPages: [2] };
  const persisted = updateRunWorkUnit(snapshot, completed, result);
  assert.deepEqual(persisted.artifacts[0], { workUnitId: completed.id, value: result });
});

test("completed planner visual-region work cannot be stored without its result artifact", () => {
  const run = transitionRun(createAnalysisRun({ sourceFingerprint: fingerprint, createdAt, runKey: "planner-visual-artifact" }), "running", createdAt);
  const snapshot = { schemaVersion: 1, run, plan: null, workUnits: [], artifacts: [] };
  const pending = createWorkUnit({ runId: run.id, kind: "extract", sourceIds: ["doc:page:2:image:1"], ordinal: 0, createdAt, operationKey: "planned_visual_region_extraction:action" });
  const running = transitionWorkUnit(pending, "running", createdAt);
  const completed = transitionWorkUnit(running, "completed", createdAt);

  assert.throws(() => updateRunWorkUnit(snapshot, completed), /must have a persisted result artifact/);
  const result = { ok: true, parsed: { requirements: [{ page: 2, quote: "Pressure shall remain below 2 Pa." }] }, allowedPages: [2] };
  const persisted = updateRunWorkUnit(snapshot, completed, result);
  assert.deepEqual(persisted.artifacts[0], { workUnitId: completed.id, value: result });
});

test("local store configuration refuses ephemeral hosted filesystems and stays off without a key", () => {
  assert.equal(createLocalRunStoreFromEnvironment({}), null);
  assert.throws(() => createLocalRunStoreFromEnvironment({ VERCEL: "1", TCE_RUN_STORE_KEY: keyHex }), /not durable on Vercel/);
});
