import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";
import { chmodSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import type { AnalysisRun, ModelProposalEnvelope, TaskPlanProposal, WorkUnit } from "./analysis-run";

const STORE_VERSION = 1;
const MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024;
const AAD_PREFIX = "tce-analysis-run:v1:";

export type RunArtifact = { workUnitId: string; value: unknown };

export type PersistedRunSnapshot = {
  schemaVersion: 1;
  run: AnalysisRun;
  plan: ModelProposalEnvelope<TaskPlanProposal> | null;
  workUnits: WorkUnit[];
  artifacts: RunArtifact[];
  finalResult?: unknown;
};

export type AnalysisRunStore = {
  save(snapshot: PersistedRunSnapshot): void;
  load(runId: string): PersistedRunSnapshot | null;
  close(): void;
};

export function updateRunPlan(snapshot: PersistedRunSnapshot, plan: ModelProposalEnvelope<TaskPlanProposal>): PersistedRunSnapshot {
  const updated = { ...snapshot, plan };
  validateSnapshot(updated);
  return updated;
}

export function updateRunState(snapshot: PersistedRunSnapshot, run: AnalysisRun): PersistedRunSnapshot {
  const updated = { ...snapshot, run };
  validateSnapshot(updated);
  return updated;
}

export function updateRunFinalResult(snapshot: PersistedRunSnapshot, run: AnalysisRun, finalResult: unknown): PersistedRunSnapshot {
  const updated = { ...snapshot, run, finalResult };
  validateSnapshot(updated);
  return updated;
}

export function updateRunWorkUnit(snapshot: PersistedRunSnapshot, unit: WorkUnit, artifactValue?: unknown): PersistedRunSnapshot {
  const workUnits = [...snapshot.workUnits];
  const existingIndex = workUnits.findIndex((candidate) => candidate.id === unit.id);
  if (existingIndex >= 0) workUnits[existingIndex] = unit;
  else workUnits.push(unit);
  let artifacts = snapshot.artifacts.filter((artifact) => artifact.workUnitId !== unit.id);
  if (unit.status === "completed" && artifactValue !== undefined) artifacts.push({ workUnitId: unit.id, value: artifactValue });
  const updated = { ...snapshot, workUnits, artifacts };
  validateSnapshot(updated);
  return updated;
}

function validateSnapshot(snapshot: PersistedRunSnapshot): void {
  if (!snapshot || typeof snapshot !== "object" || snapshot.schemaVersion !== STORE_VERSION
    || !snapshot.run || typeof snapshot.run !== "object" || !/^run_[a-f0-9]{32}$/i.test(snapshot.run.id)
    || !/^[a-f0-9]{64}$/i.test(snapshot.run.sourceFingerprint)
    || !/^[a-f0-9]{64}$/i.test(snapshot.run.configFingerprint)
    || !["queued", "running", "paused", "failed", "completed", "cancelled"].includes(snapshot.run.status)
    || !Number.isSafeInteger(snapshot.run.revision) || snapshot.run.revision < 0
    || !Number.isFinite(Date.parse(snapshot.run.createdAt)) || !Number.isFinite(Date.parse(snapshot.run.updatedAt))
    || !Array.isArray(snapshot.workUnits) || !Array.isArray(snapshot.artifacts)
    || (snapshot.plan !== null && (snapshot.plan?.schemaVersion !== 1 || snapshot.plan.runId !== snapshot.run.id
      || snapshot.plan.sourceFingerprint !== snapshot.run.sourceFingerprint))) throw new Error("The run snapshot is malformed.");
  if (snapshot.finalResult !== undefined) {
    const finalResult = snapshot.finalResult as { document?: { documentFingerprint?: unknown }; requirements?: unknown } | null;
    if (!finalResult || finalResult.document?.documentFingerprint !== snapshot.run.sourceFingerprint
      || !Array.isArray(finalResult.requirements)) throw new Error("The run snapshot contains an invalid final result.");
  }
  const unitIds = new Set<string>();
  for (const unit of snapshot.workUnits) {
    if (!unit || unit.runId !== snapshot.run.id || typeof unit.idempotencyKey !== "string"
      || unit.id !== unit.idempotencyKey || unitIds.has(unit.id) || !Array.isArray(unit.sourceIds) || unit.sourceIds.length === 0
      || unit.sourceIds.some((id) => typeof id !== "string" || !id) || new Set(unit.sourceIds).size !== unit.sourceIds.length
      || !Number.isSafeInteger(unit.ordinal) || unit.ordinal < 0 || !Number.isSafeInteger(unit.attempt) || unit.attempt < 0
      || typeof unit.operation !== "string" || !unit.operation
      || !["plan", "inspect", "extract", "validate", "coverage"].includes(unit.kind)
      || !["pending", "running", "retryable", "blocked", "completed", "cancelled"].includes(unit.status)
      || !Number.isFinite(Date.parse(unit.createdAt)) || !Number.isFinite(Date.parse(unit.updatedAt))) throw new Error("The run snapshot contains an invalid work unit.");
    unitIds.add(unit.id);
  }
  const artifactIds = new Set<string>();
  for (const artifact of snapshot.artifacts) {
    if (!artifact || !unitIds.has(artifact.workUnitId) || artifactIds.has(artifact.workUnitId)) {
      throw new Error("The run snapshot contains an unbound or duplicate result artifact.");
    }
    artifactIds.add(artifact.workUnitId);
  }
  for (const unit of snapshot.workUnits) {
    if (unit.status === "completed" && ["page_routing", "visual_table_extraction"].includes(unit.operation) && !artifactIds.has(unit.id)) {
      throw new Error("A completed model work unit must have a persisted result artifact.");
    }
  }
  if (snapshot.finalResult !== undefined && snapshot.run.status !== "completed") {
    throw new Error("A final analysis result requires a completed run state.");
  }
  let encoded: string;
  try { encoded = JSON.stringify(snapshot); } catch { throw new Error("The run snapshot contains a value that cannot be serialized."); }
  if (Buffer.byteLength(encoded, "utf8") > MAX_SNAPSHOT_BYTES) throw new Error("The encrypted run snapshot exceeds the local storage limit.");
}

function keyFromHex(keyHex: string): Buffer {
  if (!/^[a-f0-9]{64}$/i.test(keyHex)) throw new Error("TCE_RUN_STORE_KEY must be a 64-character hexadecimal AES-256 key.");
  return Buffer.from(keyHex, "hex");
}

function encrypt(snapshot: PersistedRunSnapshot, key: Buffer): { iv: Buffer; ciphertext: Buffer } {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  cipher.setAAD(Buffer.from(`${AAD_PREFIX}${snapshot.run.id}`, "utf8"));
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(snapshot), "utf8"), cipher.final(), cipher.getAuthTag()]);
  return { iv, ciphertext };
}

function decrypt(runId: string, iv: Uint8Array, ciphertextAndTag: Uint8Array, key: Buffer): PersistedRunSnapshot {
  if (ciphertextAndTag.byteLength < 16 || ciphertextAndTag.byteLength > MAX_SNAPSHOT_BYTES + 16) {
    throw new Error("The encrypted run snapshot is malformed or exceeds the storage limit.");
  }
  const bytes = Buffer.from(ciphertextAndTag);
  const decipher = createDecipheriv("aes-256-gcm", key, Buffer.from(iv));
  decipher.setAAD(Buffer.from(`${AAD_PREFIX}${runId}`, "utf8"));
  decipher.setAuthTag(bytes.subarray(bytes.length - 16));
  let plaintext: Buffer;
  try {
    plaintext = Buffer.concat([decipher.update(bytes.subarray(0, -16)), decipher.final()]);
  } catch {
    throw new Error("The run snapshot could not be authenticated with this key.");
  }
  let snapshot: PersistedRunSnapshot;
  try {
    snapshot = JSON.parse(plaintext.toString("utf8")) as PersistedRunSnapshot;
  } catch {
    throw new Error("The decrypted run snapshot is not valid JSON.");
  }
  validateSnapshot(snapshot);
  if (snapshot.run.id !== runId) throw new Error("The run snapshot identity does not match its storage key.");
  return snapshot;
}

/** Encrypted SQLite adapter for a private/local Node runtime. No tender body is stored in plaintext. */
export function createEncryptedSQLiteRunStore(input: { databasePath: string; keyHex: string }): AnalysisRunStore {
  const key = keyFromHex(input.keyHex);
  const databasePath = resolve(input.databasePath);
  mkdirSync(dirname(databasePath), { recursive: true, mode: 0o700 });
  const database = new DatabaseSync(databasePath);
  chmodSync(databasePath, 0o600);
  database.exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;");
  database.exec(`
    CREATE TABLE IF NOT EXISTS analysis_runs (
      run_id TEXT PRIMARY KEY,
      schema_version INTEGER NOT NULL,
      updated_at TEXT NOT NULL,
      iv BLOB NOT NULL,
      ciphertext_and_tag BLOB NOT NULL
    ) STRICT;
  `);
  const saveStatement = database.prepare(`
    INSERT INTO analysis_runs(run_id, schema_version, updated_at, iv, ciphertext_and_tag)
    VALUES(?, ?, ?, ?, ?)
    ON CONFLICT(run_id) DO UPDATE SET
      schema_version = excluded.schema_version,
      updated_at = excluded.updated_at,
      iv = excluded.iv,
      ciphertext_and_tag = excluded.ciphertext_and_tag
  `);
  const loadStatement = database.prepare("SELECT schema_version, iv, ciphertext_and_tag FROM analysis_runs WHERE run_id = ?");
  return {
    save(snapshot) {
      validateSnapshot(snapshot);
      const encrypted = encrypt(snapshot, key);
      saveStatement.run(snapshot.run.id, STORE_VERSION, snapshot.run.updatedAt, encrypted.iv, encrypted.ciphertext);
    },
    load(runId) {
      if (!/^run_[a-f0-9]{32}$/i.test(runId)) throw new Error("A valid analysis run ID is required.");
      const row = loadStatement.get(runId) as { schema_version: number; iv: Uint8Array; ciphertext_and_tag: Uint8Array } | undefined;
      if (!row) return null;
      if (row.schema_version !== STORE_VERSION) throw new Error("The stored run uses an unsupported schema version.");
      return decrypt(runId, row.iv, row.ciphertext_and_tag, key);
    },
    close() { database.close(); },
  };
}

/** Hosted/serverless filesystems are ephemeral; refuse to call them durable. */
export function createLocalRunStoreFromEnvironment(env: NodeJS.ProcessEnv = process.env): AnalysisRunStore | null {
  const keyHex = env.TCE_RUN_STORE_KEY?.trim();
  if (!keyHex) return null;
  if (env.VERCEL === "1" || env.VERCEL_ENV) throw new Error("The local SQLite run store is not durable on Vercel. Configure a hosted persistence adapter before enabling hosted resume.");
  const databasePath = env.TCE_RUN_STORE_PATH?.trim() || resolve(process.cwd(), ".local", "analysis-runs.sqlite");
  return createEncryptedSQLiteRunStore({ databasePath, keyHex });
}
