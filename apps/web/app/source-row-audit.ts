export type SourceRowAuditStatus = "no_gap_reported" | "possible_gap" | "ambiguous" | "incomplete";

export type SourceRowAuditInput = {
  rowIndex: number;
  sourceCells: string[];
  extractedRequirements: string[];
};

export type SourceRowAuditResult = {
  rowIndex: number;
  status: Exclude<SourceRowAuditStatus, "incomplete">;
  note: string;
  /** Literal source excerpts the advisory audit believes are not represented in the draft. */
  missingSourceQuotes: string[];
};

export const SOURCE_ROW_AUDIT_MAX_CHARS = 12_000;
export const SOURCE_ROW_AUDIT_MAX_ROWS = 12;
export const SOURCE_ROW_AUDIT_MAX_BATCHES_PER_ANALYSIS = 16;

function sourceRowAuditInputSize(row: SourceRowAuditInput): number {
  return row.sourceCells.reduce((sum, cell) => sum + cell.length, 0) + row.extractedRequirements.reduce((sum, quote) => sum + quote.length, 0);
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
  sourceRows: SourceRowAuditInput[] = [],
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
    if (!Array.isArray(row.missing_source_quotes) || row.missing_source_quotes.length > 8
      || row.missing_source_quotes.some((quote) => typeof quote !== "string" || !quote.trim() || quote.length > 1_000)) return { complete: false, rows: [] };
    const sourceRow = sourceRows.find((candidate) => candidate.rowIndex === row.row_index);
    const sourceCells = sourceRow?.sourceCells ?? [];
    const missingSourceQuotes = row.missing_source_quotes as string[];
    if (row.status !== "possible_gap" && missingSourceQuotes.length > 0) return { complete: false, rows: [] };
    if (missingSourceQuotes.some((quote) => !sourceCells.some((cell) => cell.includes(quote)))) return { complete: false, rows: [] };
    observed.add(row.row_index as number);
    rows.push({ rowIndex: row.row_index as number, status: row.status, note: row.note, missingSourceQuotes: [...new Set(missingSourceQuotes)] });
  }
  if (observed.size !== expected.size) return { complete: false, rows: [] };
  return { complete: true, rows: rows.sort((left, right) => left.rowIndex - right.rowIndex) };
}
