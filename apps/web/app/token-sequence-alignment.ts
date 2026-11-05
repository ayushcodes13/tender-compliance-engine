/**
 * Deterministic Exact Token Sequence Alignment and Spatial Grounding Engine
 *
 * Implements strict, deterministic 1:1 token sequence matching between quotes
 * and document text (native PDF text items or OCR lines).
 *
 * ZERO FUZZY MATCHING POLICY:
 * - No Levenshtein edit distance
 * - No heuristic similarity thresholds (0.70 / 0.80)
 * - No word dropping or skipping
 * - Every token in the query must match the document token with 100% exact equality (t1 === t2)
 *
 * Deterministic Canonicalization:
 * - Unifies dash glyphs (—, –, −, ―) -> -
 * - Unifies plus-minus notations (±, +/-) -> +
 * - Strips leading/trailing bullet artifacts and boundary punctuation
 * - Case-insensitive comparison (lowercase)
 * - Bridges line wraps, carriage returns, and multi-whitespace formatting differences
 * - Derives exact bounding boxes from the underlying spatially-bound tokens
 */

export type BoundingBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type SpatiallyBoundToken = {
  raw: string;
  norm: string;
  start: number;
  end: number;
};

export type SequenceAlignmentMatch = {
  startOffset: number;
  endOffset: number;
  score: number;
  matchedTokensCount: number;
};

/**
 * Normalizes an individual token for comparison:
 * - Unifies dash glyphs (—, –, −, ―) -> -
 * - Unifies plus-minus notations (±, +/-) -> +
 * - Strips leading/trailing bullet artifacts and punctuation
 * - Normalizes to lowercase
 */
export function normalizeToken(token: string): string {
  return token
    .toLowerCase()
    .replace(/[\u2014\u2013\u2212\u2015]/g, "-")
    .replace(/[\u00b1]|(\+\s*\/\s*-)/g, "+")
    .replace(/^[«¢•●▪■◆★*›»\-.,;:()\[\]{}"'\/]+|[.,;:()\[\]{}"'\/]+$/g, "")
    .trim();
}

/**
 * Tokenizes text into non-whitespace tokens with their character offsets.
 */
export function tokenizeText(text: string): SpatiallyBoundToken[] {
  const tokens: SpatiallyBoundToken[] = [];
  const regex = /\S+/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    const raw = match[0];
    const norm = normalizeToken(raw);
    if (norm.length > 0) {
      tokens.push({
        raw,
        norm,
        start: match.index,
        end: match.index + raw.length,
      });
    }
  }
  return tokens;
}

/**
 * Strict binary token equality (100% exact match).
 * Returns 1.0 if tokens match exactly, 0.0 otherwise.
 * ZERO fuzzy edit distance.
 */
export function tokenSimilarity(t1: string, t2: string): number {
  return t1 === t2 ? 1.0 : 0.0;
}

/**
 * Aligns a query quote against a document text stream using deterministic exact token sequence matching.
 * Returns the character start and end offsets in documentText, or null if no exact token sequence match exists.
 *
 * Every single token in the query MUST match the corresponding document token with exact equality (===).
 */
export function alignExactTokenSequence(
  query: string,
  documentText: string,
): SequenceAlignmentMatch | null {
  const Q = tokenizeText(query);
  const D = tokenizeText(documentText);

  if (Q.length === 0 || D.length === 0 || Q.length > D.length) {
    return null;
  }

  // Find exact 1:1 contiguous sequence match
  for (let i = 0; i <= D.length - Q.length; i += 1) {
    let exactMatch = true;
    for (let k = 0; k < Q.length; k += 1) {
      if (Q[k].norm !== D[i + k].norm) {
        exactMatch = false;
        break;
      }
    }

    if (exactMatch) {
      return {
        startOffset: D[i].start,
        endOffset: D[i + Q.length - 1].end,
        score: 1.0,
        matchedTokensCount: Q.length,
      };
    }
  }

  return null;
}

/** Backward compatibility alias */
export const alignTokenSequence = alignExactTokenSequence;

/**
 * Locates the bounding box for a quote in a spatially-mapped page
 * using deterministic exact token sequence alignment.
 */
export function locateQuoteSequenceAlignment(
  quote: string,
  rawText: string,
  rawItemMap: number[],
  positioned: Array<{ start: number; end: number; box: BoundingBox }>,
): BoundingBox | null {
  if (!quote?.trim() || !rawText?.trim() || !positioned || positioned.length === 0) {
    return null;
  }

  const match = alignExactTokenSequence(quote, rawText);
  if (!match) return null;

  const used = new Set<number>();
  for (let i = match.startOffset; i < match.endOffset; i += 1) {
    const itemIndex = rawItemMap[i];
    if (itemIndex !== undefined && itemIndex >= 0) used.add(itemIndex);
  }

  const boxes = [...used]
    .map((index) => positioned[index]?.box)
    .filter((box): box is BoundingBox => Boolean(box && box.width > 0 && box.height > 0));

  if (boxes.length === 0) return null;

  const x = Math.min(...boxes.map((box) => box.x));
  const y = Math.min(...boxes.map((box) => box.y));
  const right = Math.max(...boxes.map((box) => box.x + box.width));
  const bottom = Math.max(...boxes.map((box) => box.y + box.height));

  if (![x, y, right, bottom].every(Number.isFinite) || right <= x || bottom <= y) {
    return null;
  }

  return { x, y, width: right - x, height: bottom - y };
}
