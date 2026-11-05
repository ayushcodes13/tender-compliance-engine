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

const CASE_SENSITIVE_UNITS_SET = new Set([
  'mw', 'mW', 'MW', 'kw', 'kW', 'KW', 'w', 'W',
  'ma', 'mA', 'MA', 'a', 'A', 'ua', 'uA', 'µa', 'µA',
  'mhz', 'mHz', 'MHz', 'khz', 'kHz', 'ghz', 'GHz', 'hz', 'Hz',
  'db', 'dB', 'dbc', 'dBc',
  'mbar', 'Mbar', 'bar', 'Bar',
  'mv', 'mV', 'MV', 'v', 'V', 'kv', 'kV',
  'ml', 'mL', 'ML', 'l', 'L', 'ul', 'uL', 'µl', 'µL',
  'mg', 'Mg', 'g', 'G', 'kg', 'KG',
  'mj', 'mJ', 'MJ', 'j', 'J', 'kj', 'kJ',
  'pa', 'Pa', 'kpa', 'kPa', 'mpa', 'MPa', 'gpa', 'GPa',
  'b', 'B', 'kb', 'kB', 'mb', 'MB', 'gb', 'GB', 'tb', 'TB', 'bit', 'Bit',
  'c', 'C', '°c', '°C', 'k', 'K',
]);

/**
 * Normalizes an individual token for comparison:
 * - Unifies dash glyphs (—, –, −, ―) -> -
 * - Unifies plus-minus notations (±, +/-) -> ± (preserves ± distinction from +)
 * - Strips leading/trailing bullet artifacts and punctuation
 * - Preserves leading minus sign if immediately followed by a digit (signed numbers like -20)
 * - Preserves case for SI units and prefixes (MW vs mW, MA vs mA)
 */
export function normalizeToken(token: string): string {
  // 1. Unify dash glyphs (em-dash, en-dash, minus, horizontal bar) -> '-'
  let s = token.replace(/[\u2014\u2013\u2212\u2015]/g, "-");

  // 2. Unify plus-minus notations (±, +/-) -> '±' (never collapse ± into +)
  s = s.replace(/[\u00b1]|(?:\+\s*\/\s*-)/g, "±");

  // 3. Strip leading bullet characters and boundary punctuation, but PRESERVE negative sign if followed by a digit
  s = s.replace(/^[«¢•●▪■◆★*›».,;:()\[\]{}"'\/]+|^-(?!\d)/g, "");

  // 4. Strip trailing boundary punctuation
  s = s.replace(/[.,;:()\[\]{}"'\/]+$/g, "").trim();

  // 5. Preserve case for known SI units and engineering symbols
  if (CASE_SENSITIVE_UNITS_SET.has(s)) {
    return s;
  }

  // Attached number-unit tokens (e.g. "500mW", "20MA", "100MHz", "±0.5dB")
  const numUnitMatch = s.match(/^([±+-]?\d+(?:\.\d+)?)([a-zA-Z°µ]+)$/);
  if (numUnitMatch) {
    const [, num, unit] = numUnitMatch;
    if (CASE_SENSITIVE_UNITS_SET.has(unit)) {
      return `${num}${unit}`;
    }
  }

  return s.toLowerCase();
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
 * Returns the character start and end offsets in documentText, or null if no exact token sequence match exists
 * (or if requireUnique is true and multiple occurrences exist).
 *
 * Every single token in the query MUST match the corresponding document token with exact equality (===).
 */
export function alignExactTokenSequence(
  query: string,
  documentText: string,
  options?: { requireUnique?: boolean },
): SequenceAlignmentMatch | null {
  const requireUnique = options?.requireUnique ?? false;
  const Q = tokenizeText(query);
  const D = tokenizeText(documentText);

  if (Q.length === 0 || D.length === 0 || Q.length > D.length) {
    return null;
  }

  const matches: SequenceAlignmentMatch[] = [];

  for (let i = 0; i <= D.length - Q.length; i += 1) {
    let exactMatch = true;
    for (let k = 0; k < Q.length; k += 1) {
      if (Q[k].norm !== D[i + k].norm) {
        exactMatch = false;
        break;
      }
    }

    if (exactMatch) {
      matches.push({
        startOffset: D[i].start,
        endOffset: D[i + Q.length - 1].end,
        score: 1.0,
        matchedTokensCount: Q.length,
      });
      if (requireUnique && matches.length > 1) {
        return null;
      }
    }
  }

  if (requireUnique && matches.length > 1) {
    return null;
  }

  return matches[0] ?? null;
}

/** Backward compatibility alias */
export const alignTokenSequence = alignExactTokenSequence;

/**
 * Checks for technical value agreement between a claim and source passage:
 * - SI prefix case sensitivity (MW vs mW, MA vs mA)
 * - Number signs (-20 vs 20)
 * - Tolerance operators (± vs +)
 * - Directional operators (min vs max)
 * - Negation
 */
export function hasTechnicalAgreement(claim: string, evidence: string): boolean {
  // 1. Signed numbers must agree
  const claimSignedNums = (claim.match(/[+-]?\d+(?:\.\d+)?/g) || []);
  const evidenceSignedNums = (evidence.match(/[+-]?\d+(?:\.\d+)?/g) || []);
  if (claimSignedNums.length > 0 || evidenceSignedNums.length > 0) {
    if (claimSignedNums.length !== evidenceSignedNums.length) return false;
    for (let i = 0; i < claimSignedNums.length; i += 1) {
      if (claimSignedNums[i] !== evidenceSignedNums[i]) return false;
    }
  }

  // 2. Tolerance / plus-minus operators
  const claimHasPlusMinus = /[\u00b1]|(?:\+\s*\/\s*-)/.test(claim);
  const evidenceHasPlusMinus = /[\u00b1]|(?:\+\s*\/\s*-)/.test(evidence);
  if (claimHasPlusMinus !== evidenceHasPlusMinus) return false;

  // 3. Case-sensitive SI units
  for (const unit of ['MW', 'mW', 'MA', 'mA', 'MHz', 'mHz', 'GHz', 'kHz', 'mbar', 'Mbar', 'mL', 'ML', 'mg', 'Mg']) {
    const claimHasUnit = new RegExp(`\\b${unit}\\b`).test(claim);
    const evidenceHasUnit = new RegExp(`\\b${unit}\\b`).test(evidence);
    if (claimHasUnit !== evidenceHasUnit) {
      return false;
    }
  }

  // 4. Directional operators
  const isClaimMin = /\b(?:min|minimum|at least|greater|>=|>)\b/i.test(claim);
  const isClaimMax = /\b(?:max|maximum|at most|less|<=|<)\b/i.test(claim);
  const isEvidMin = /\b(?:min|minimum|at least|greater|>=|>)\b/i.test(evidence);
  const isEvidMax = /\b(?:max|maximum|at most|less|<=|<)\b/i.test(evidence);
  if (isClaimMin && isEvidMax) return false;
  if (isClaimMax && isEvidMin) return false;

  // 5. Negation
  const claimNeg = /\b(?:not|without|never|no)\b/i.test(claim);
  const evidNeg = /\b(?:not|without|never|no)\b/i.test(evidence);
  if (claimNeg !== evidNeg) return false;

  return true;
}

/**
 * Searches rawText for quote using strict token-bounded matching.
 * Returns the exact unique match span, or null if 0 matches or multiple (ambiguous) matches exist.
 * Verifies that technical units, numbers, and signs do not diverge.
 */
export function findUniqueTokenBoundedMatch(
  rawText: string,
  quote: string,
): { startOffset: number; endOffset: number; sourceText: string } | null {
  const target = quote.replace(/\s+/g, " ").trim();
  if (!target || !rawText?.trim()) return null;

  // Build searchable text with collapsed whitespace, tracking raw character offsets
  let searchable = "";
  const rawOffsets: number[] = [];
  let inWhitespace = false;

  for (let i = 0; i < rawText.length; i += 1) {
    const char = rawText[i];
    if (/\s/.test(char)) {
      if (!inWhitespace) {
        searchable += " ";
        rawOffsets.push(i);
      }
      inWhitespace = true;
    } else {
      searchable += char;
      rawOffsets.push(i);
      inWhitespace = false;
    }
  }

  // Scan for all token-bounded occurrences of target in searchable
  let startIndex = 0;
  const matches: Array<{ startOffset: number; endOffset: number; sourceText: string }> = [];

  while (startIndex <= searchable.length - target.length) {
    const idx = searchable.indexOf(target, startIndex);
    if (idx < 0) break;

    // Enforce token boundaries: character before and after must not be word characters [a-zA-Z0-9]
    const isStartBounded = idx === 0 || !/[a-zA-Z0-9]/.test(searchable[idx - 1]);
    const endPos = idx + target.length;
    const isEndBounded = endPos === searchable.length || !/[a-zA-Z0-9]/.test(searchable[endPos]);

    if (isStartBounded && isEndBounded) {
      const rawStart = rawOffsets[idx];
      const rawEnd = rawOffsets[idx + target.length - 1] + 1;
      const matchedSourceText = rawText.slice(rawStart, rawEnd);

      if (hasTechnicalAgreement(target, matchedSourceText)) {
        matches.push({
          startOffset: rawStart,
          endOffset: rawEnd,
          sourceText: matchedSourceText,
        });
      }
    }

    startIndex = idx + 1; // Advance by 1 to check overlapping matches
  }

  if (matches.length === 1) {
    return matches[0];
  }

  // If exact substring was not found or was ambiguous, check exact token sequence with requireUnique
  if (matches.length === 0) {
    const seq = alignExactTokenSequence(quote, rawText, { requireUnique: true });
    if (seq) {
      const sourceText = rawText.slice(seq.startOffset, seq.endOffset);
      if (hasTechnicalAgreement(quote, sourceText)) {
        return {
          startOffset: seq.startOffset,
          endOffset: seq.endOffset,
          sourceText,
        };
      }
    }
  }

  return null;
}

/**
 * Locates the bounding box for a quote in a spatially-mapped page
 * using deterministic exact token sequence alignment.
 * Requires uniqueness by default to prevent highlighting ambiguous repeated passages.
 */
export function locateQuoteSequenceAlignment(
  quote: string,
  rawText: string,
  rawItemMap: number[],
  positioned: Array<{ start: number; end: number; box: BoundingBox }>,
  options?: { requireUnique?: boolean },
): BoundingBox | null {
  if (!quote?.trim() || !rawText?.trim() || !positioned || positioned.length === 0) {
    return null;
  }

  const match = alignExactTokenSequence(quote, rawText, { requireUnique: options?.requireUnique ?? true });
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
