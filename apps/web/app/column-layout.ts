export type SourceColumnRole = "serial" | "heading" | "specification" | "quantity" | "remark" | "compliance" | "deviation" | "other";
export type SourceColumn = { header: string; role: SourceColumnRole };

/** A lone content column holds requirements; a separate parameter column is optional. */
export function normalizeSingleContentColumn(columns: SourceColumn[]): SourceColumn[] {
  if(columns.some(column=>column.role==='specification'))return columns;
  const content=columns.filter(column=>!['serial','quantity','compliance','deviation','remark'].includes(column.role));
  if(content.length!==1||content[0].role!=='heading')return columns;
  return columns.map(column=>column===content[0]?{...column,role:'specification'}:column);
}

function matchesTokenWithBoundaries(token: string, text: string): boolean {
  if (token === "sl") {
    return /\b(?:sl|sil|s1|si)\b/i.test(text);
  }
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`, "i").test(text);
}

/** Check whether a candidate header's tokens exist in raw or OCR page text within a coherent header window with strict token boundaries. */
export function matchOcrHeaderTokens(header: string, pageText: string): boolean {
  if (!pageText || !header.trim()) return false;
  const lowerHeader = header.toLowerCase().replace(/\s+/g, " ").trim();
  const tokens = lowerHeader.replace(/[^a-z0-9]/g, " ").split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return false;

  const lines = pageText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  for (let i = 0; i < lines.length; i += 1) {
    const combinedWindow = i + 1 < lines.length ? `${lines[i]} ${lines[i + 1]}` : lines[i];
    const allTokensMatch = tokens.every((token) => matchesTokenWithBoundaries(token, combinedWindow));
    if (allTokensMatch) return true;
  }

  return false;
}

const roles = new Set<SourceColumnRole>([
  "serial", "heading", "specification", "quantity", "remark", "compliance", "deviation", "other",
]);

function normalizeHeader(value: string): string {
  return value.replace(/\s+/g, " ").trim();
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

