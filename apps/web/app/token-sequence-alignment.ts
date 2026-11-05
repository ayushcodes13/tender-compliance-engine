/**
 * Token-Level Sequence Alignment and Spatial Grounding Engine
 *
 * Implements resilient token sequence alignment between LLM-extracted quotes
 * and document text (native PDF text items or OCR lines).
 *
 * Solves the "Dual-Path Divergence Problem" permanently:
 * - Tolerates OCR symbol substitutions (± vs +, em-dash vs en-dash vs hyphen)
 * - Tolerates OCR character noise (rn vs m, 0 vs O, 1 vs l)
 * - Tolerates bullet glyphs («, ¢, •, ●, ▪, ■, ◆, ★, *, ›, »)
 * - Handles multi-line table wraps and trailing punctuation
 * - Derives exact bounding boxes from the underlying spatially-bound tokens
 * - Strictly rejects hallucinations (similarity score < 0.70)
 * - Strictly rejects semantic false positives (changed numbers, units, directional operators, or negation)
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
 * Calculates Levenshtein edit distance between two strings.
 */
export function levenshteinDistance(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const v0 = new Array<number>(b.length + 1);
  const v1 = new Array<number>(b.length + 1);
  for (let i = 0; i <= b.length; i += 1) v0[i] = i;
  for (let i = 0; i < a.length; i += 1) {
    v1[0] = i + 1;
    for (let j = 0; j < b.length; j += 1) {
      const cost = a[i] === b[j] ? 0 : 1;
      v1[j + 1] = Math.min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost);
    }
    for (let j = 0; j <= b.length; j += 1) v0[j] = v1[j];
  }
  return v1[b.length];
}

/**
 * Computes normalized similarity between two tokens in [0.0, 1.0].
 * Short tokens (<= 2 chars) require exact match to prevent false positives.
 */
export function tokenSimilarity(t1: string, t2: string): number {
  if (t1 === t2) return 1.0;
  const maxLen = Math.max(t1.length, t2.length);
  if (maxLen <= 2) return t1 === t2 ? 1.0 : 0.0;
  const dist = levenshteinDistance(t1, t2);
  const sim = 1.0 - dist / maxLen;
  return sim >= 0.75 ? sim : 0.0;
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

const COMMON_TECHNICAL_UNITS = new Set([
  'bar', 'mbar', 'rpm', 'mw', 'kw', 'w', 'db', 'dbc', 'kg', 'g', 'mg', 'mm', 'cm',
  'm', 's', 'sec', 'msec', 'usec', 'hz', 'khz', 'mhz', 'ghz', 'k', 'c', 'v', 'mv',
  'a', 'ma', 'ul', 'ml', 'l', 'ohm', 'spins', 'points', 'bit', 'psi', 'pa', 'kpa', 'mpa',
]);

/**
 * Extracts normalized numbers from a list of tokens.
 * Handles decimals and comma thousand separators (e.g. "1,000" -> "1000", "500" -> "500", "0.5" -> "0.5").
 */
export function extractNormalizedNumbers(tokens: SpatiallyBoundToken[]): string[] {
  const nums: string[] = [];
  for (const t of tokens) {
    const raw = t.raw.replace(/,/g, '');
    const matches = raw.match(/\d+(?:\.\d+)?/g);
    if (matches) {
      for (const m of matches) {
        nums.push(m.includes('.') ? String(parseFloat(m)) : m);
      }
    }
  }
  return nums;
}

/**
 * Identifies directional inequality operators in a token sequence.
 */
export function getInequalityDirection(tokens: SpatiallyBoundToken[]): 'min' | 'max' | 'none' {
  const minWords = new Set(['min', 'minimum', 'least', 'greater', '>=', '>', 'above']);
  const maxWords = new Set(['max', 'maximum', 'most', 'less', '<=', '<', 'below']);
  let hasMin = false;
  let hasMax = false;
  for (const t of tokens) {
    const norm = t.norm;
    if (minWords.has(norm)) hasMin = true;
    if (maxWords.has(norm)) hasMax = true;
  }
  if (hasMin && !hasMax) return 'min';
  if (hasMax && !hasMin) return 'max';
  return 'none';
}

/**
 * Checks for negation markers in a token sequence.
 */
export function hasNegation(tokens: SpatiallyBoundToken[]): boolean {
  const negWords = new Set(['not', 'no', 'never', 'without', 'except', 'excluding', 'non']);
  return tokens.some((t) => negWords.has(t.norm));
}

/**
 * Extracts technical physical units from a token sequence.
 */
export function extractTechnicalUnits(tokens: SpatiallyBoundToken[]): string[] {
  const units: string[] = [];
  for (const t of tokens) {
    const unitPart = t.norm.replace(/[^a-z]/g, '');
    if (COMMON_TECHNICAL_UNITS.has(unitPart)) {
      units.push(unitPart);
    }
  }
  return units;
}

/**
 * Evaluates semantic agreement between query and candidate window.
 * Strictly rejects adversarial false positives:
 * 1. Numbers must agree exactly (e.g. 500 bar vs 200 bar is rejected).
 * 2. Directional operators must not contradict (e.g. minimum vs maximum is rejected).
 * 3. Negation polarity must match (e.g. without vs with is rejected).
 * 4. Technical units must agree.
 */
export function hasSemanticAgreement(
  queryTokens: SpatiallyBoundToken[],
  windowTokens: SpatiallyBoundToken[],
): boolean {
  // 1. Critical Numbers Agreement
  const qNums = extractNormalizedNumbers(queryTokens);
  const wNums = extractNormalizedNumbers(windowTokens);
  if (qNums.length > 0) {
    for (const qn of qNums) {
      if (!wNums.includes(qn)) {
        return false;
      }
    }
    if (wNums.length > 0) {
      for (const wn of wNums) {
        if (!qNums.includes(wn)) {
          return false;
        }
      }
    }
  }

  // 2. Directional Inequality Agreement (min vs max)
  const qDir = getInequalityDirection(queryTokens);
  const wDir = getInequalityDirection(windowTokens);
  if (qDir !== 'none' && wDir !== 'none' && qDir !== wDir) {
    return false;
  }

  // 3. Negation Polarity Agreement
  const qNeg = hasNegation(queryTokens);
  const wNeg = hasNegation(windowTokens);
  if (qNeg !== wNeg) {
    return false;
  }

  // 4. Technical Units Agreement
  const qUnits = extractTechnicalUnits(queryTokens);
  const wUnits = extractTechnicalUnits(windowTokens);
  if (qUnits.length > 0) {
    for (const qu of qUnits) {
      if (!wUnits.includes(qu)) {
        return false;
      }
    }
    if (wUnits.length > 0) {
      for (const wu of wUnits) {
        if (!qUnits.includes(wu)) {
          return false;
        }
      }
    }
  }

  return true;
}

/**
 * Aligns a query quote against a document text stream using sliding window sequence alignment.
 * Returns the character start and end offsets in documentText, or null if no valid match.
 */
export function alignTokenSequence(
  query: string,
  documentText: string,
  options?: { minScore?: number; maxLookahead?: number },
): SequenceAlignmentMatch | null {
  const minScore = options?.minScore ?? 0.70;
  const maxLookahead = options?.maxLookahead ?? 3;

  const Q = tokenizeText(query);
  const D = tokenizeText(documentText);

  if (Q.length === 0 || D.length === 0) return null;

  let bestScore = 0;
  let bestSpan: { startIdx: number; endIdx: number; score: number } | null = null;

  const minLen = Math.max(1, Math.floor(Q.length * 0.70));
  const maxLen = Math.ceil(Q.length * 1.30);

  for (let i = 0; i < D.length; i += 1) {
    // Quick anchor check: document token must align with Q[0] or Q[1]
    const firstSim = Math.max(
      tokenSimilarity(D[i].norm, Q[0].norm),
      Q.length > 1 ? tokenSimilarity(D[i].norm, Q[1].norm) * 0.8 : 0,
    );
    if (firstSim < 0.6) continue;

    for (let len = minLen; len <= maxLen && i + len <= D.length; len += 1) {
      const window = D.slice(i, i + len);

      // Perform semantic agreement check first; do not allow number or operator divergence
      if (!hasSemanticAgreement(Q, window)) {
        continue;
      }

      let matchedWeight = 0;
      let wIdx = 0;
      for (let qIdx = 0; qIdx < Q.length; qIdx += 1) {
        let bestMatch = 0;
        let bestW = -1;
        const lookaheadLimit = Math.min(window.length, wIdx + maxLookahead);
        for (let look = wIdx; look < lookaheadLimit; look += 1) {
          const sim = tokenSimilarity(Q[qIdx].norm, window[look].norm);
          if (sim > bestMatch) {
            bestMatch = sim;
            bestW = look;
          }
        }
        if (bestMatch >= 0.70) {
          matchedWeight += bestMatch;
          wIdx = bestW + 1;
        }
      }

      const score = matchedWeight / Math.max(Q.length, window.length);
      if (score > bestScore) {
        bestScore = score;
        bestSpan = {
          startIdx: i,
          endIdx: i + len - 1,
          score,
        };
      }
    }
  }

  if (bestScore >= minScore && bestSpan) {
    const finalWindow = D.slice(bestSpan.startIdx, bestSpan.endIdx + 1);
    if (!hasSemanticAgreement(Q, finalWindow)) {
      return null;
    }

    return {
      startOffset: D[bestSpan.startIdx].start,
      endOffset: D[bestSpan.endIdx].end,
      score: bestScore,
      matchedTokensCount: bestSpan.endIdx - bestSpan.startIdx + 1,
    };
  }

  return null;
}

/**
 * Locates the bounding box for a quote in a spatially-mapped page
 * using token sequence alignment.
 */
export function locateQuoteSequenceAlignment(
  quote: string,
  rawText: string,
  rawItemMap: number[],
  positioned: Array<{ start: number; end: number; box: BoundingBox }>,
  options?: { minScore?: number },
): BoundingBox | null {
  if (!quote?.trim() || !rawText?.trim() || !positioned || positioned.length === 0) {
    return null;
  }

  const match = alignTokenSequence(quote, rawText, options);
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
