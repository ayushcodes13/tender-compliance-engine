export type SourceRowAuditStatus = "no_gap_reported" | "possible_gap" | "ambiguous" | "incomplete";

export type SourceRowAuditInput = {
  rowIndex: number;
  sourceText: string;
  extractedRequirements: string[];
};

export type SourceRowAuditResult = {
  rowIndex: number;
  status: Exclude<SourceRowAuditStatus, "incomplete">;
  note: string;
};

export const SOURCE_ROW_AUDIT_MAX_CHARS = 12_000;
export const SOURCE_ROW_AUDIT_MAX_ROWS = 12;
export const SOURCE_ROW_AUDIT_MAX_BATCHES_PER_ANALYSIS = 16;

function sourceRowAuditInputSize(row: SourceRowAuditInput): number {
  return row.sourceText.length + row.extractedRequirements.reduce((sum, quote) => sum + quote.length, 0);
}

export function isSourceRowAuditBatchWithinLimits(
  rows: SourceRowAuditInput[],
  limits: { maxRows?: number; maxChars?: number } = {},
): boolean {
  return rows.length <= (limits.maxRows ?? SOURCE_ROW_AUDIT_MAX_ROWS)
    && rows.reduce((sum, row) => sum + sourceRowAuditInputSize(row), 0) <= (limits.maxChars ?? SOURCE_ROW_AUDIT_MAX_CHARS);
}

export function batchSourceRowsForAudit(
  rows: SourceRowAuditInput[],
  limits: { maxRows?: number; maxChars?: number } = {},
): SourceRowAuditInput[][] {
  const maxRows = limits.maxRows ?? SOURCE_ROW_AUDIT_MAX_ROWS;
  const maxChars = limits.maxChars ?? SOURCE_ROW_AUDIT_MAX_CHARS;
  if (!Number.isInteger(maxRows) || maxRows < 1 || !Number.isInteger(maxChars) || maxChars < 1) return [];
  const batches: SourceRowAuditInput[][] = [];
  let batch: SourceRowAuditInput[] = [];
  let size = 0;
  for (const row of rows) {
    const rowSize = sourceRowAuditInputSize(row);
    if (batch.length && (batch.length >= maxRows || size + rowSize > maxChars)) {
      batches.push(batch);
      batch = [];
      size = 0;
    }
    batch.push(row);
    size += rowSize;
    if (batch.length === 1 && size > maxChars) {
      batches.push(batch);
      batch = [];
      size = 0;
    }
  }
  if (batch.length) batches.push(batch);
  return batches;
}

export function validateSourceRowAuditResult(
  value: unknown,
  expectedRowIndices: number[],
): { complete: true; rows: SourceRowAuditResult[] } | { complete: false; rows: [] } {
  if (!value || typeof value !== "object" || !Array.isArray((value as { rows?: unknown }).rows)) return { complete: false, rows: [] };
  const input = (value as { rows: unknown[] }).rows;
  if (input.length !== expectedRowIndices.length) return { complete: false, rows: [] };
  const expected = new Set(expectedRowIndices);
  const observed = new Set<number>();
  const rows: SourceRowAuditResult[] = [];
  for (const item of input) {
    if (!item || typeof item !== "object") return { complete: false, rows: [] };
    const row = item as Record<string, unknown>;
    if (!Number.isInteger(row.row_index) || !expected.has(row.row_index as number) || observed.has(row.row_index as number)) return { complete: false, rows: [] };
    if (row.status !== "no_gap_reported" && row.status !== "possible_gap" && row.status !== "ambiguous") return { complete: false, rows: [] };
    if (typeof row.note !== "string" || row.note.length > 500) return { complete: false, rows: [] };
    observed.add(row.row_index as number);
    rows.push({ rowIndex: row.row_index as number, status: row.status, note: row.note });
  }
  if (observed.size !== expected.size) return { complete: false, rows: [] };
  return { complete: true, rows: rows.sort((left, right) => left.rowIndex - right.rowIndex) };
}
