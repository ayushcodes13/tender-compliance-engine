import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { createAnalysisRun, createWorkUnit, executeWorkUnit, transitionRun, transitionWorkUnit } from "./analysis-run.ts";
import { createEncryptedSQLiteRunStore, createLocalRunStoreFromEnvironment, updateRunFinalResult, updateRunState, updateRunWorkUnit } from "./run-store.ts";

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
    workUnits: [unit],
    artifacts: [{ workUnitId: unit.id, value: { text: "CONFIDENTIAL_TEST_REQUIREMENT_731" } }],
  };
}

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
    const analysis = { document: { documentFingerprint: fingerprint }, requirements: [] };
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

test("local store configuration refuses ephemeral hosted filesystems and stays off without a key", () => {
  assert.equal(createLocalRunStoreFromEnvironment({}), null);
  assert.throws(() => createLocalRunStoreFromEnvironment({ VERCEL: "1", TCE_RUN_STORE_KEY: keyHex }), /not durable on Vercel/);
});
