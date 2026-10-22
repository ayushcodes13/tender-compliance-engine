export type SourceColumnRole = "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other";
export type SourceColumn = { header: string; role: SourceColumnRole };

const roles = new Set<SourceColumnRole>([
  "serial", "heading", "specification", "quantity", "remark", "compliance", "deviation", "other",
]);

function normalizeHeader(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLocaleLowerCase();
}

/** Accept a model-proposed page layout only when every label is literal source text. */
export function validatePageColumnMap(
  value: unknown,
  sourceCells: string[],
  matchesSourceText?: (header: string) => boolean,
): SourceColumn[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const columns: SourceColumn[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return null;
    const column = item as { header?: unknown; role?: unknown };
    if (typeof column.header !== "string" || !column.header.trim() || !roles.has(column.role as SourceColumnRole)) return null;
    const header = column.header.trim();
    if (!sourceCells.some((cell) => normalizeHeader(cell) === normalizeHeader(header))
      && !matchesSourceText?.(header)) return null;
    columns.push({ header, role: column.role as SourceColumnRole });
  }
  return columns;
}

/** A single response-sheet schema is safe only when visible page layouts agree exactly. */
export function sameColumnLayout(left: SourceColumn[], right: SourceColumn[]): boolean {
  return left.length === right.length && left.every((column, index) =>
    normalizeHeader(column.header) === normalizeHeader(right[index].header)
      && column.role === right[index].role);
}

export function findColumnLayoutConflict(
  expected: SourceColumn[],
  observations: Array<{ page: number; columns: SourceColumn[]; invalid?: boolean }>,
): number | undefined {
  return observations.find((observation) => observation.invalid
    || (observation.columns.length > 0 && expected.length > 0
      && !sameColumnLayout(expected, observation.columns)))?.page;
}

