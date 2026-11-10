import { createHash } from "node:crypto";

/** Source-bound runtime state for one requested analysis; encrypted persistence is supplied by run-store.ts. */
export type AnalysisRunStatus = "queued" | "running" | "paused" | "failed" | "completed" | "cancelled";
export type WorkUnitStatus = "pending" | "running" | "retryable" | "blocked" | "completed" | "cancelled";
export type WorkKind = "plan" | "inspect" | "extract" | "validate" | "coverage";
export const ANALYSIS_PIPELINE_VERSION = "phase1-v2-runtime-4";

export type AnalysisRun = {
  id: string;
  sourceFingerprint: string;
  configFingerprint: string;
  status: AnalysisRunStatus;
  createdAt: string;
  updatedAt: string;
  revision: number;
};

export type WorkUnit = {
  id: string;
  idempotencyKey: string;
  runId: string;
  kind: WorkKind;
  sourceIds: string[];
  /** Requested bounded operation, or the work kind when not operation-specific. */
  operation: string;
  ordinal: number;
  status: WorkUnitStatus;
  attempt: number;
  createdAt: string;
  updatedAt: string;
};

export type PlanScopeDisposition = "relevant" | "possibly_relevant" | "unresolved" | "outside_task";
export type InspectionMode = "native_text" | "table" | "ocr" | "visual" | "cross_page";

/** Flexible semantic proposal inside a stable run/source envelope; never trusted without validation. */
export type PlanDecision = "continue" | "stop" | "needs_review";

export type TaskPlanProposal = {
  decision: PlanDecision;
  decisionRationale: string;
  task: string;
  scope: Array<{ sourceIds: string[]; disposition: PlanScopeDisposition; rationale: string }>;
  sections: Array<{ label: string; sourceIds: string[] }>;
  actions: Array<{ mode: InspectionMode; sourceIds: string[]; rationale: string }>;
  openQuestions: string[];
};

export type ModelProposalEnvelope<T> = {
  schemaVersion: 1;
  runId: string;
  sourceFingerprint: string;
  proposal: T;
};

export type PlanningRoundOutcome = {
  sourceId: string;
  mode?: InspectionMode;
  status: "executed" | "deferred" | "failed" | "unresolved";
  /** Short operational summary only; document text belongs in encrypted work artifacts. */
  summary: string;
};

/** Append-only record of one model decision against a bounded view of run state. */
export type PersistedPlanningRound = {
  roundIndex: number;
  inputFingerprint: string;
  plan: ModelProposalEnvelope<TaskPlanProposal>;
  decision: PlanDecision;
  outcomes: PlanningRoundOutcome[];
  createdAt: string;
};

const RUN_TRANSITIONS: Record<AnalysisRunStatus, readonly AnalysisRunStatus[]> = {
  queued: ["running", "cancelled"],
  running: ["paused", "failed", "completed", "cancelled"],
  paused: ["running", "cancelled"],
  failed: ["running", "cancelled"],
  completed: [],
  cancelled: [],
};

const UNIT_TRANSITIONS: Record<WorkUnitStatus, readonly WorkUnitStatus[]> = {
  pending: ["running", "cancelled"],
  running: ["retryable", "blocked", "completed", "cancelled"],
  retryable: ["running", "cancelled"],
  blocked: ["running", "cancelled"],
  completed: [],
  cancelled: ["running"],
};

function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function validTimestamp(value: string): boolean {
  return Number.isFinite(Date.parse(value));
}

export function createAnalysisRun(input: {
  sourceFingerprint: string;
  configFingerprint?: string;
  createdAt: string;
  runKey: string;
}): AnalysisRun {
  if (!/^[a-f0-9]{64}$/i.test(input.sourceFingerprint)) throw new Error("A run requires a SHA-256 source fingerprint.");
  if (!input.runKey.trim()) throw new Error("A run requires a non-empty caller-provided run key.");
  if (!validTimestamp(input.createdAt)) throw new Error("A run requires a valid creation timestamp.");
  const configFingerprint = input.configFingerprint ?? digest("phase1-default-config");
  if (!/^[a-f0-9]{64}$/i.test(configFingerprint)) throw new Error("A run requires a SHA-256 configuration fingerprint.");
  return {
    id: `run_${digest([input.sourceFingerprint.toLowerCase(), configFingerprint.toLowerCase(), input.runKey]).slice(0, 32)}`,
    sourceFingerprint: input.sourceFingerprint.toLowerCase(),
    configFingerprint: configFingerprint.toLowerCase(),
    status: "queued",
    createdAt: input.createdAt,
    updatedAt: input.createdAt,
    revision: 0,
  };
}

export function transitionRun(run: AnalysisRun, status: AnalysisRunStatus, at: string): AnalysisRun {
  if (!validTimestamp(at) || Date.parse(at) < Date.parse(run.updatedAt)) throw new Error("Run transition time must be valid and monotonic.");
  if (!RUN_TRANSITIONS[run.status].includes(status)) throw new Error(`Illegal analysis run transition: ${run.status} -> ${status}.`);
  return { ...run, status, updatedAt: at, revision: run.revision + 1 };
}

export function createWorkUnit(input: {
  runId: string;
  kind: WorkKind;
  sourceIds: string[];
  ordinal: number;
  createdAt: string;
  operationKey?: string;
}): WorkUnit {
  const sourceIds = [...new Set(input.sourceIds)].sort();
  if (!input.runId.trim()) throw new Error("A work unit requires a run ID.");
  if (sourceIds.length === 0 || sourceIds.length !== input.sourceIds.length) throw new Error("A work unit requires unique, non-empty source IDs.");
  if (!Number.isSafeInteger(input.ordinal) || input.ordinal < 0) throw new Error("A work unit requires a non-negative integer ordinal.");
  if (!validTimestamp(input.createdAt)) throw new Error("A work unit requires a valid creation timestamp.");
  const operation = input.operationKey ?? input.kind;
  const identity = [input.runId, input.kind, sourceIds, operation];
  const idempotencyKey = `work_${digest(identity)}`;
  return {
    id: idempotencyKey,
    idempotencyKey,
    runId: input.runId,
    kind: input.kind,
    sourceIds,
    operation,
    ordinal: input.ordinal,
    status: "pending",
    attempt: 0,
    createdAt: input.createdAt,
    updatedAt: input.createdAt,
  };
}

export function transitionWorkUnit(unit: WorkUnit, status: WorkUnitStatus, at: string): WorkUnit {
  if (!validTimestamp(at) || Date.parse(at) < Date.parse(unit.updatedAt)) throw new Error("Work-unit transition time must be valid and monotonic.");
  if (!UNIT_TRANSITIONS[unit.status].includes(status)) throw new Error(`Illegal work-unit transition: ${unit.status} -> ${status}.`);
  return { ...unit, status, updatedAt: at, attempt: unit.attempt + (status === "running" ? 1 : 0) };
}

/** Executes one unit and exposes transition callbacks so a caller can durably persist state and output.
 */
export async function executeWorkUnit<T>(input: {
  unit: WorkUnit;
  execute: () => Promise<T>;
  isSuccessful: (result: T) => boolean;
  now?: () => string;
  signal?: AbortSignal;
  onState?: (unit: WorkUnit) => Promise<void> | void;
  onResult?: (unit: WorkUnit, result: T) => Promise<void> | void;
}): Promise<{ unit: WorkUnit; result?: T; error?: unknown }> {
  const now = input.now ?? (() => new Date().toISOString());
  if (input.unit.status !== "pending" && input.unit.status !== "retryable" && input.unit.status !== "blocked" && input.unit.status !== "cancelled") {
    throw new Error(`Work unit ${input.unit.id} is not eligible to execute from ${input.unit.status}.`);
  }
  let unit = transitionWorkUnit(input.unit, "running", now());
  try {
    await input.onState?.(unit);
  } catch (error) {
    const retryable = transitionWorkUnit(unit, "retryable", now());
    return { unit: retryable, error };
  }
  let result: T;
  try {
    result = await input.execute();
  } catch (error) {
    unit = transitionWorkUnit(unit, input.signal?.aborted ? "cancelled" : "retryable", now());
    try { await input.onState?.(unit); } catch { /* Keep the original execution failure visible. */ }
    return { unit, error };
  }
  let succeeded: boolean;
  try {
    succeeded = input.isSuccessful(result);
  } catch (error) {
    const retryable = transitionWorkUnit(unit, "retryable", now());
    try { await input.onState?.(retryable); } catch { /* Keep the validator failure visible. */ }
    return { unit: retryable, error };
  }
  const updated = transitionWorkUnit(unit, succeeded ? "completed" : "retryable", now());
  try {
    if (succeeded && input.onResult) await input.onResult(updated, result);
    else await input.onState?.(updated);
    return { unit: updated, result };
  } catch (error) {
    const retryable = transitionWorkUnit(unit, "retryable", now());
    try { await input.onState?.(retryable); } catch { /* Persistence is already the reported failure. */ }
    return { unit: retryable, error };
  }
}

/** Stable execution order regardless of provider completion order or input permutation. */
export function orderWorkUnits(units: readonly WorkUnit[]): WorkUnit[] {
  const seen = new Set<string>();
  for (const unit of units) {
    if (seen.has(unit.idempotencyKey)) throw new Error(`Duplicate work-unit idempotency key: ${unit.idempotencyKey}.`);
    seen.add(unit.idempotencyKey);
  }
  return [...units].sort((a, b) => a.ordinal - b.ordinal || a.id.localeCompare(b.id));
}
