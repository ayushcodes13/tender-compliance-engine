import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { chmodSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import type { AnalysisRun, ModelProposalEnvelope, PersistedPlanningRound, PlanningRoundOutcome, TaskPlanProposal, WorkUnit } from "./analysis-run";

const STORE_VERSION = 1;
const MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024;
const AAD_PREFIX = "tce-analysis-run:v1:";

export type RunArtifact = { workUnitId: string; value: unknown };

export type PersistedRunSnapshot = {
  schemaVersion: 1;
  run: AnalysisRun;
  plan: ModelProposalEnvelope<TaskPlanProposal> | null;
  /** Append-only planning history. `plan` remains an alias for the latest proposal for older callers. */
  planningRounds?: PersistedPlanningRound[];
  workUnits: WorkUnit[];
  artifacts: RunArtifact[];
  finalResult?: unknown;
};

export const MAX_PLANNING_ROUNDS = 8;
export const MAX_PLANNING_OUTCOMES = 240;
export const MAX_PLANNING_OUTCOME_SUMMARY_CHARS = 300;

export type AnalysisRunStore = {
  save(snapshot: PersistedRunSnapshot): void;
  load(runId: string): PersistedRunSnapshot | null;
  close(): void;
};

export function updateRunPlan(snapshot: PersistedRunSnapshot, plan: ModelProposalEnvelope<TaskPlanProposal>, requestFingerprint?: string): PersistedRunSnapshot {
  const inputFingerprint = requestFingerprint ?? createHash("sha256").update(JSON.stringify(plan)).digest("hex");
  return appendPlanningRound(snapshot, {
    inputFingerprint,
    plan,
    outcomes: [],
    createdAt: snapshot.run.updatedAt,
  });
}

export function latestPlanningRound(snapshot: PersistedRunSnapshot): PersistedPlanningRound | null {
  const rounds = snapshot.planningRounds ?? [];
  return rounds.length ? rounds[rounds.length - 1] : null;
}

export function appendPlanningRound(snapshot: PersistedRunSnapshot, input: {
  inputFingerprint: string;
  plan: ModelProposalEnvelope<TaskPlanProposal>;
  outcomes: PlanningRoundOutcome[];
  createdAt: string;
}): PersistedRunSnapshot {
  const rounds = snapshot.planningRounds ?? [];
  const latestIndex = rounds.at(-1)?.roundIndex ?? -1;
  if (rounds.length >= MAX_PLANNING_ROUNDS) throw new Error("The planning round limit was reached.");
  const round: PersistedPlanningRound = {
    roundIndex: latestIndex + 1,
    inputFingerprint: input.inputFingerprint,
    plan: input.plan,
    decision: input.plan.proposal.decision,
    outcomes: input.outcomes.map((outcome) => ({ ...outcome })),
    createdAt: input.createdAt,
  };
  const updated = { ...snapshot, plan: input.plan, planningRounds: [...rounds, round] };
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
    || (snapshot.planningRounds !== undefined && !Array.isArray(snapshot.planningRounds))
    || (snapshot.plan !== null && (snapshot.plan?.schemaVersion !== 1 || snapshot.plan.runId !== snapshot.run.id
      || snapshot.plan.sourceFingerprint !== snapshot.run.sourceFingerprint))) throw new Error("The run snapshot is malformed.");
  const rounds = snapshot.planningRounds ?? [];
  if (rounds.length > MAX_PLANNING_ROUNDS) throw new Error("The run snapshot exceeds the planning round limit.");
  const roundIndexes = new Set<number>();
  for (const round of rounds) {
    if (!round || !Number.isSafeInteger(round.roundIndex) || round.roundIndex < 0
      || round.roundIndex !== roundIndexes.size || roundIndexes.has(round.roundIndex)
      || !/^[a-f0-9]{64}$/i.test(round.inputFingerprint)
      || !Number.isFinite(Date.parse(round.createdAt))
      || !["continue", "stop", "needs_review"].includes(round.decision)
      || round.plan?.schemaVersion !== 1 || round.plan.runId !== snapshot.run.id
      || round.plan.sourceFingerprint !== snapshot.run.sourceFingerprint
      || !round.plan.proposal || typeof round.plan.proposal.decisionRationale !== "string"
      || round.plan.proposal.decisionRationale.length > 500 || !round.plan.proposal.decisionRationale.trim()
      || round.plan.proposal.decision !== round.decision
      || !Array.isArray(round.outcomes) || round.outcomes.length > MAX_PLANNING_OUTCOMES) {
      throw new Error("The run snapshot contains an invalid planning round.");
    }
    const outcomeSources = new Set<string>();
    for (const outcome of round.outcomes) {
      if (!outcome || typeof outcome.sourceId !== "string" || !outcome.sourceId.trim()
        || (outcome.mode !== undefined && !["native_text", "table", "ocr", "visual", "cross_page"].includes(outcome.mode))
        || outcomeSources.has(`${outcome.mode ?? "unknown"}:${outcome.sourceId}`)
        || !["executed", "deferred", "failed", "unresolved"].includes(outcome.status)
        || typeof outcome.summary !== "string" || outcome.summary.length > MAX_PLANNING_OUTCOME_SUMMARY_CHARS) {
        throw new Error("The run snapshot contains an invalid planning outcome.");
      }
      outcomeSources.add(`${outcome.mode ?? "unknown"}:${outcome.sourceId}`);
    }
    roundIndexes.add(round.roundIndex);
  }
  if (rounds.length && (!snapshot.plan || JSON.stringify(snapshot.plan) !== JSON.stringify(rounds.at(-1)!.plan))) {
    throw new Error("The latest planning round must match the compatibility plan alias.");
  }
  if (snapshot.finalResult !== undefined) {
    const finalResult = snapshot.finalResult as { document?: { documentFingerprint?: unknown }; requirements?: unknown; completionStatus?: unknown } | null;
    if (!finalResult || finalResult.document?.documentFingerprint !== snapshot.run.sourceFingerprint
      || !Array.isArray(finalResult.requirements)
      || !["complete", "partial"].includes(finalResult.completionStatus as string)) throw new Error("The run snapshot contains an invalid final result.");
    if ((snapshot.run.status === "completed" && finalResult.completionStatus !== "complete")
      || (snapshot.run.status === "paused" && finalResult.completionStatus !== "partial")
      || !["completed", "paused"].includes(snapshot.run.status)) {
      throw new Error("The saved analysis state does not match its persisted completion result.");
    }
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
    if (unit.status === "completed" && (["page_routing", "visual_table_extraction", "general_requirement_extraction", "table"].includes(unit.operation)
      || unit.operation.startsWith("planned_native_text_extraction:") || unit.operation.startsWith("planned_ocr_extraction:")
      || unit.operation.startsWith("planned_visual_region_extraction:")) && !artifactIds.has(unit.id)) {
      throw new Error("A completed model work unit must have a persisted result artifact.");
    }
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
  let parsedSnapshot: unknown;
  try {
    parsedSnapshot = JSON.parse(plaintext.toString("utf8")) as unknown;
  } catch {
    throw new Error("The decrypted run snapshot is not valid JSON.");
  }
  const snapshot = migrateLegacyPlanningRounds(parsedSnapshot);
  validateSnapshot(snapshot);
  if (snapshot.run.id !== runId) throw new Error("The run snapshot identity does not match its storage key.");
  return snapshot;
}

/** Adds an explicit review-safe round record when opening a pre-round snapshot. */
function migrateLegacyPlanningRounds(value: unknown): PersistedRunSnapshot {
  if (!value || typeof value !== "object") throw new Error("The decrypted run snapshot is not valid JSON.");
  const snapshot = value as PersistedRunSnapshot;
  if (Array.isArray(snapshot.planningRounds)) return snapshot;
  if (!snapshot.run || !Array.isArray(snapshot.workUnits) || !Array.isArray(snapshot.artifacts)) {
    throw new Error("The decrypted run snapshot is malformed.");
  }
  if (!snapshot.plan) return { ...snapshot, planningRounds: [] };
  if (!snapshot.plan.proposal || typeof snapshot.plan.proposal !== "object") {
    throw new Error("The decrypted run snapshot contains an invalid legacy plan.");
  }
  const proposal = snapshot.plan.proposal as TaskPlanProposal & { decision?: unknown; decisionRationale?: unknown };
  const decision = proposal.decision === "continue" || proposal.decision === "stop" || proposal.decision === "needs_review"
    ? proposal.decision : "needs_review";
  const migratedPlan: ModelProposalEnvelope<TaskPlanProposal> = {
    ...snapshot.plan,
    proposal: {
      ...proposal,
      decision,
      decisionRationale: typeof proposal.decisionRationale === "string" && proposal.decisionRationale.trim()
        ? proposal.decisionRationale.slice(0, 500)
        : "Legacy one-shot plan migrated without a recorded adaptive decision; human review is required.",
    },
  };
  const inputFingerprint = createHash("sha256").update(JSON.stringify(migratedPlan)).digest("hex");
  const round: PersistedPlanningRound = {
    roundIndex: 0,
    inputFingerprint,
    plan: migratedPlan,
    decision,
    outcomes: [],
    createdAt: snapshot.run.updatedAt,
  };
  return { ...snapshot, plan: migratedPlan, planningRounds: [round] };
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
