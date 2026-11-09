import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { DatabaseSync } from "node:sqlite";
import { createAnalysisRun, createWorkUnit } from "./analysis-run.ts";
import { createEncryptedSQLiteRunStore, createLocalRunStoreFromEnvironment } from "./run-store.ts";

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

test("local store configuration refuses ephemeral hosted filesystems and stays off without a key", () => {
  assert.equal(createLocalRunStoreFromEnvironment({}), null);
  assert.throws(() => createLocalRunStoreFromEnvironment({ VERCEL: "1", TCE_RUN_STORE_KEY: keyHex }), /not durable on Vercel/);
});
