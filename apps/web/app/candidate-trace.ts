import { createHash, randomUUID } from "node:crypto";
import { chmod, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

export type CandidateOrigin = "initial_extraction" | "vector_table_extraction" | "source_row_recovery" | "text_page_omission_audit" | "visual_page_omission_audit";
export type CandidateDisposition = "accepted" | "rejected" | "duplicate" | "merged" | "discarded" | "incomplete";

export type CandidateTraceInput = {
  documentFingerprint: string;
  page: number | null;
  origin: CandidateOrigin;
  modelQuote: string;
  sourceQuote: string | null;
  sourceQuoteStatus: "matched" | "unavailable";
  sourceElementIds?: string[];
  sourceRowIndex?: number;
  sourceColumnIndex?: number;
  candidateOrdinal?: number;
  sourceRowId?: string;
  sourceCellId?: string;
};

export type CandidateTraceRecord = CandidateTraceInput & {
  candidateId: string;
  disposition: CandidateDisposition;
  responsibleStage: string;
  rejectionCategory?: string;
  finalRequirementId?: string;
  relatedCandidateId?: string;
};

export type ExpectedSourceUnit = {
  expectedUnitId: string;
  page: number;
  sourceQuote: string;
  sourceElementIds?: string[];
};

export type ExpectedSourceUnitResult = ExpectedSourceUnit & {
  status: "not_generated" | "generated_accepted" | "generated_rejected" | "generated_duplicate" | "generated_merged" | "generated_discarded" | "generated_incomplete";
  candidateIds: string[];
};

export function resolveForensicTraceConfig(env: NodeJS.ProcessEnv = process.env): { enabled: boolean; directory: string | null } {
  const hosted = Boolean(env.VERCEL || env.VERCEL_ENV);
  if (env.TCE_FORENSIC_TRACE !== "1" || hosted) return { enabled: false, directory: null };
  return { enabled: true, directory: path.resolve(process.cwd(), ".local", "forensic-traces") };
}

const normalize = (value: string) => value.replace(/\s+/g, " ").trim();

export class CandidateTraceLedger {
  private readonly entries = new Map<string, CandidateTraceRecord>();
  private readonly occurrences = new Map<string, number>();
  readonly documentFingerprint: string;

  constructor(documentFingerprint: string) {
    this.documentFingerprint = documentFingerprint;
  }

  register(input: Omit<CandidateTraceInput, "documentFingerprint">): string {
    const base = {
      ...input,
      documentFingerprint: this.documentFingerprint,
      sourceElementIds: [...new Set(input.sourceElementIds ?? [])].sort(),
    };
    const identity = JSON.stringify({
      documentFingerprint: base.documentFingerprint,
      page: base.page,
      origin: base.origin,
      quote: normalize(base.modelQuote),
      sourceElementIds: base.sourceElementIds,
      sourceRowIndex: base.sourceRowIndex,
      sourceColumnIndex: base.sourceColumnIndex,
      candidateOrdinal: base.candidateOrdinal,
    });
    const digest = createHash("sha256").update(identity).digest("hex").slice(0, 24);
    const occurrence = this.occurrences.get(digest) ?? 0;
    this.occurrences.set(digest, occurrence + 1);
    const candidateId = `cand-${digest}${occurrence ? `-${occurrence + 1}` : ""}`;
    this.entries.set(candidateId, {
      ...base,
      candidateId,
      disposition: "incomplete",
      responsibleStage: "pending",
    });
    return candidateId;
  }

  terminate(candidateId: string, result: {
    disposition: Exclude<CandidateDisposition, "incomplete">;
    responsibleStage: string;
    rejectionCategory?: string;
    finalRequirementId?: string;
    relatedCandidateId?: string;
  }): void {
    const prior = this.entries.get(candidateId);
    if (!prior || prior.disposition !== "incomplete") return;
    this.entries.set(candidateId, { ...prior, ...result });
  }

  get records(): CandidateTraceRecord[] {
    return [...this.entries.values()];
  }

  finalize(): CandidateTraceRecord[] {
    for (const [candidateId, entry] of this.entries) {
      if (entry.disposition === "incomplete") {
        this.entries.set(candidateId, {
          ...entry,
          responsibleStage: "trace_integrity",
          rejectionCategory: "candidate_terminal_disposition_missing",
        });
      }
    }
    return this.records;
  }

  summary(): Record<CandidateDisposition | "total", number> {
    const counts: Record<CandidateDisposition | "total", number> = {
      total: this.entries.size,
      accepted: 0,
      rejected: 0,
      duplicate: 0,
      merged: 0,
      discarded: 0,
      incomplete: 0,
    };
    for (const entry of this.entries.values()) counts[entry.disposition] += 1;
    return counts;
  }
}

export function compareExpectedSourceUnits(
  expected: ExpectedSourceUnit[],
  candidates: CandidateTraceRecord[],
): ExpectedSourceUnitResult[] {
  return expected.map((unit) => {
    const expectedIds = new Set(unit.sourceElementIds ?? []);
    const quote = normalize(unit.sourceQuote);
    const matches = candidates.filter((candidate) => candidate.page === unit.page
      && candidate.sourceQuoteStatus === "matched"
      && normalize(candidate.sourceQuote ?? "").includes(quote)
      && (expectedIds.size === 0 || candidate.sourceElementIds?.some((id) => expectedIds.has(id))));
    const byId = new Map(matches.map((candidate) => [candidate.candidateId, candidate]));
    const dispositions = [...byId.values()].map((candidate) => candidate.disposition);
    const selected = dispositions.includes("accepted") ? "generated_accepted"
      : dispositions.includes("rejected") ? "generated_rejected"
        : dispositions.includes("duplicate") ? "generated_duplicate"
          : dispositions.includes("merged") ? "generated_merged"
            : dispositions.includes("discarded") ? "generated_discarded"
              : dispositions.includes("incomplete") ? "generated_incomplete"
                : "not_generated";
    return { ...unit, status: selected, candidateIds: [...byId.keys()] };
  });
}

export async function writeForensicTrace(
  directory: string,
  input: { documentFingerprint: string; candidates: CandidateTraceRecord[]; expectedSourceUnits?: ExpectedSourceUnit[] },
): Promise<string> {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  await chmod(directory, 0o700);
  const candidates = input.candidates;
  const summary = candidates.reduce<Record<CandidateDisposition | "total", number>>((counts, candidate) => {
    counts.total += 1;
    counts[candidate.disposition] += 1;
    return counts;
  }, { total: 0, accepted: 0, rejected: 0, duplicate: 0, merged: 0, discarded: 0, incomplete: 0 });
  const trace = {
    schemaVersion: 1,
    traceRunId: randomUUID(),
    documentFingerprint: input.documentFingerprint,
    createdAt: new Date().toISOString(),
    summary,
    candidates,
    ...(input.expectedSourceUnits ? {
      expectedSourceUnits: input.expectedSourceUnits,
      expectedSourceUnitResults: compareExpectedSourceUnits(input.expectedSourceUnits, candidates),
    } : {}),
  };
  const target = path.join(directory, `${input.documentFingerprint}-${trace.traceRunId}.json`);
  await writeFile(target, `${JSON.stringify(trace, null, 2)}\n`, { encoding: "utf8", mode: 0o600, flag: "wx" });
  await chmod(target, 0o600);
  return target;
}
