/**
 * Tiered Citation Validation Layer
 *
 * Implements the Phase 1 validation ladder:
 * 1. Tier 1 (Verbatim Check - Deterministic):
 *    Strict exact token containment on native PDF selectable text.
 *    If passed -> verdict: "verbatim_pass", precision: "exact".
 *
 * 2. Tier 2 (Visual Check):
 *    Fallback when verbatim fails (e.g. scanned pages, OCR noise, multi-line table wrapping).
 *    Checks OCR transcript tokens and visual evidence.
 *    If passed -> verdict: "visual_pass", precision: "visual-ocr".
 *
 * 3. Tier 3 (Human Review):
 *    Fallback when both verbatim and visual checks fail.
 *    The requirement is NOT discarded or hallucinated into passing;
 *    it is explicitly flagged as needing human review.
 *    -> verdict: "needs_human_review", precision: "unverified", needsHumanReview: true.
 */

import { alignTokenSequence, findUniqueTokenBoundedMatch, normalizeToken } from "./token-sequence-alignment.ts";

export type BoundingBox = { x: number; y: number; width: number; height: number };

export type ValidationVerdict = "verbatim_pass" | "visual_pass" | "needs_human_review";

export type TieredValidationInput = {
  id: string;
  quote: string;
  text?: string;
  page: number;
  rowType?: "section" | "requirement" | "optional_heading";
};

export type PageEvidenceSource = {
  page: number;
  rawText: string;
  rawItemMap?: number[];
  positioned?: Array<{ start: number; end: number; box: BoundingBox }>;
  ocrText?: string;
  ocrRawItemMap?: number[];
  ocrPositioned?: Array<{ start?: number; end?: number; box: BoundingBox; text?: string; ocrConfidenceLevel?: "high" | "medium" | "low" }>;
  ocrPerformed?: boolean;
};

export type ValidatedEvidenceResult = {
  id: string;
  verdict: ValidationVerdict;
  precision: "exact" | "visual-ocr" | "unverified";
  needsHumanReview: boolean;
  method: "pdfjs-native-text" | "tesseract-ocr" | "unverified";
  bbox: BoundingBox | null;
  ocrConfidence?: "high" | "medium" | "low";
  unverifiedReason?: string;
};

export type ValidationSummary = {
  total: number;
  verbatimPass: number;
  visualPass: number;
  needsHumanReview: number;
};

/**
 * Normalizes text for OCR comparison by reconciling common OCR symbol substitutions:
 * - Equivalent dash glyphs are normalized while numeric range separators remain explicit
 * - Plus-minus variants (±, +/-) remain distinct from positive plus signs
 * - Bullet artifacts («, ¢, •, ●, ▪, ■, ◆, ★, *, ›, ») -> stripped
 * - Word-boundary punctuation (, ; : .) -> space
 * - Ordinary words compare case-insensitively; case-sensitive engineering units retain their spelling
 */
export function normalizeOcrComparable(value: string): string {
  if (!value) return "";
  return value
    .replace(/[«¢•●▪■◆★*›»]/g, " ")
    .replace(/\+\s*\/\s*-|±/g, " ± ")
    .replace(/(?<=\d)[\u2014\u2013\u2212\u2015-](?=\d)/g, " OCRRANGEDASH ")
    .replace(/(^|\s)[\u2014\u2013\u2212\u2015-]+(?=\s|$)/g, "$1 OCRRANGEDASH ")
    .replace(/\b(?:sil|s1|si)\b/gi, "sl")
    .split(/\s+/)
    .map(normalizeToken)
    .filter(Boolean)
    .join(" ");
}

/** Exact contiguous OCR token match after safe OCR-only glyph normalization. */
export function matchesOcrQuote(quote: string, sourceText: string): boolean {
  const target = normalizeOcrComparable(quote);
  const source = normalizeOcrComparable(sourceText);
  return Boolean(target && source && alignTokenSequence(target, source));
}

/**
 * Searches OCR positioned lines with symbol tolerance and multi-line windowing
 * to locate the exact bounding box and confidence for a candidate quote.
 */
export function locateOcrQuoteTolerant(
  quote: string,
  ocrPositioned: Array<{ start?: number; end?: number; box: BoundingBox; text?: string; ocrConfidenceLevel?: "high" | "medium" | "low" }>,
): { bbox: BoundingBox; confidence: "high" | "medium" | "low" } | null {
  const normQuote = normalizeOcrComparable(quote);
  if (!normQuote || !ocrPositioned || ocrPositioned.length === 0) return null;

  // 1. A contiguous sequence on one line (allowing other text before/after)
  for (const item of ocrPositioned) {
    if (!item.text) continue;
    const normLine = normalizeOcrComparable(item.text);
    if (matchesOcrQuote(normQuote, normLine)) {
      return { bbox: item.box, confidence: item.ocrConfidenceLevel || "medium" };
    }
  }

  // 2. Multi-line window (2 to 4 consecutive lines)
  for (let i = 0; i < ocrPositioned.length; i += 1) {
    let windowText = "";
    const windowBoxes: BoundingBox[] = [];
    const confidences: Array<"high" | "medium" | "low"> = [];
    for (let j = i; j < Math.min(ocrPositioned.length, i + 4); j += 1) {
      const item = ocrPositioned[j];
      if (!item.text) continue;
      windowText += (windowText ? " " : "") + item.text;
      windowBoxes.push(item.box);
      if (item.ocrConfidenceLevel) confidences.push(item.ocrConfidenceLevel);
      const normWindow = normalizeOcrComparable(windowText);
      if (matchesOcrQuote(normQuote, normWindow)) {
        const x = Math.min(...windowBoxes.map((b) => b.x));
        const y = Math.min(...windowBoxes.map((b) => b.y));
        const right = Math.max(...windowBoxes.map((b) => b.x + b.width));
        const bottom = Math.max(...windowBoxes.map((b) => b.y + b.height));
        return {
          bbox: { x, y, width: right - x, height: bottom - y },
          confidence: confidences.includes("low") ? "low" : confidences.includes("medium") ? "medium" : "high",
        };
      }
    }
  }

  return null;
}

/** Check if text matches natively with deterministic bounding box calculation */
export function checkVerbatim(
  quote: string,
  page: PageEvidenceSource,
): { matched: boolean; bbox: BoundingBox | null } {
  if (!quote?.trim() || !page.rawText?.trim()) return { matched: false, bbox: null };

  const match = findUniqueTokenBoundedMatch(page.rawText, quote);
  if (!match) return { matched: false, bbox: null };

  // Calculate bounding box if positional data exists
  if (page.rawItemMap && page.positioned && page.positioned.length > 0) {
    const rawStart = match.startOffset;
    const rawEnd = match.endOffset;
    const used = new Set<number>();
    for (let i = rawStart; i < rawEnd; i += 1) {
      const itemIndex = page.rawItemMap[i];
      if (itemIndex !== undefined && itemIndex >= 0) used.add(itemIndex);
    }
    const boxes = [...used]
      .map((index) => page.positioned![index]?.box)
      .filter((box): box is BoundingBox => Boolean(box && box.width > 0 && box.height > 0));

    if (boxes.length > 0) {
      const x = Math.min(...boxes.map((b) => b.x));
      const y = Math.min(...boxes.map((b) => b.y));
      const right = Math.max(...boxes.map((b) => b.x + b.width));
      const bottom = Math.max(...boxes.map((b) => b.y + b.height));
      return { matched: true, bbox: { x, y, width: right - x, height: bottom - y } };
    }
  }

  return { matched: true, bbox: null };
}

/** Check if text is grounded in OCR transcript or visual tokens */
export function checkVisual(
  quote: string,
  page: PageEvidenceSource,
): { matched: boolean; bbox: BoundingBox | null; ocrConfidence?: "high" | "medium" | "low" } {
  const target = normalizeOcrComparable(quote);
  if (!target) return { matched: false, bbox: null };

  const ocrText = page.ocrText || "";
  const comparableOcr = normalizeOcrComparable(ocrText);
  if (!comparableOcr) return { matched: false, bbox: null };

  // Preserve transcript-only OCR matches and derive a box from known text offsets
  // when OCR line text is unavailable. Verify the exact matched occurrence with
  // the strict OCR comparator before trusting offsets from the looser tokenizer.
  const transcriptMatch = alignTokenSequence(quote, ocrText);
  if (transcriptMatch && matchesOcrQuote(quote, ocrText.slice(transcriptMatch.startOffset, transcriptMatch.endOffset))) {
    const matchingItems = (page.ocrPositioned ?? []).filter((item) =>
      (item.start ?? 0) < transcriptMatch.endOffset && (item.end ?? 0) > transcriptMatch.startOffset
    );
    if (matchingItems.length > 0) {
      const x = Math.min(...matchingItems.map((item) => item.box.x));
      const y = Math.min(...matchingItems.map((item) => item.box.y));
      const right = Math.max(...matchingItems.map((item) => item.box.x + item.box.width));
      const bottom = Math.max(...matchingItems.map((item) => item.box.y + item.box.height));
      const confidence = matchingItems.some((item) => item.ocrConfidenceLevel === "low") ? "low"
        : matchingItems.some((item) => item.ocrConfidenceLevel === "medium") ? "medium" : "high";
      return { matched: true, bbox: { x, y, width: right - x, height: bottom - y }, ocrConfidence: confidence };
    }
  }

  // 1. OCR-tolerant line-level matching. Only safe glyph and known OCR token
  // normalizations apply; order, numeric signs, and engineering-unit case stay strict.
  if (page.ocrPositioned && page.ocrPositioned.length > 0) {
    const tolerantMatch = locateOcrQuoteTolerant(quote, page.ocrPositioned);
    if (tolerantMatch) {
      return { matched: true, bbox: tolerantMatch.bbox, ocrConfidence: tolerantMatch.confidence };
    }
  }

  // 2. Full-text comparison still requires a contiguous token sequence.
  if (matchesOcrQuote(target, comparableOcr)) {
    return { matched: true, bbox: null, ocrConfidence: "medium" };
  }

  return { matched: false, bbox: null };
}

/**
 * Execute the 3-tier validation ladder on a single candidate requirement:
 * Verbatim -> Visual -> Needs Human Review
 */
export function validateCandidateEvidence(
  candidate: TieredValidationInput,
  page: PageEvidenceSource | undefined,
): ValidatedEvidenceResult {
  if (!page) {
    return {
      id: candidate.id,
      verdict: "needs_human_review",
      precision: "unverified",
      needsHumanReview: true,
      method: "unverified",
      bbox: null,
      unverifiedReason: `Cited PDF page ${candidate.page} was not in the processed document scope.`,
    };
  }

  const quote = candidate.quote?.trim() || candidate.text?.trim() || "";
  if (!quote) {
    return {
      id: candidate.id,
      verdict: "needs_human_review",
      precision: "unverified",
      needsHumanReview: true,
      method: "unverified",
      bbox: null,
      unverifiedReason: "Empty quote cannot be verified.",
    };
  }

  // Tier 1: Deterministic Verbatim Check against native selectable text
  const verbatimResult = checkVerbatim(quote, page);
  if (verbatimResult.matched) {
    return {
      id: candidate.id,
      verdict: "verbatim_pass",
      precision: verbatimResult.bbox ? "exact" : "visual-ocr",
      needsHumanReview: false,
      method: "pdfjs-native-text",
      bbox: verbatimResult.bbox,
    };
  }

  // Tier 2: Visual Check against OCR transcript / visual tokens
  const visualResult = checkVisual(quote, page);
  if (visualResult.matched) {
    return {
      id: candidate.id,
      verdict: "visual_pass",
      precision: "visual-ocr",
      needsHumanReview: false,
      method: "tesseract-ocr",
      bbox: visualResult.bbox,
      ocrConfidence: visualResult.ocrConfidence,
    };
  }

  // Tier 3: Human Review Fallback
  return {
    id: candidate.id,
    verdict: "needs_human_review",
    precision: "unverified",
    needsHumanReview: true,
    method: "unverified",
    bbox: null,
    unverifiedReason: `Could not verify text verbatim or visually on PDF page ${candidate.page}; marked for human review.`,
  };
}

/**
 * Run tiered validation over all candidate requirements before presenting to the user.
 */
export function runTieredValidation(
  candidates: TieredValidationInput[],
  pages: PageEvidenceSource[],
): {
  results: Map<string, ValidatedEvidenceResult>;
  summary: ValidationSummary;
} {
  const pageMap = new Map(pages.map((p) => [p.page, p]));
  const results = new Map<string, ValidatedEvidenceResult>();

  let verbatimPass = 0;
  let visualPass = 0;
  let needsHumanReview = 0;

  for (const candidate of candidates) {
    const page = pageMap.get(candidate.page);
    const result = validateCandidateEvidence(candidate, page);
    results.set(candidate.id, result);

    if (result.verdict === "verbatim_pass") verbatimPass += 1;
    else if (result.verdict === "visual_pass") visualPass += 1;
    else needsHumanReview += 1;
  }

  return {
    results,
    summary: {
      total: candidates.length,
      verbatimPass,
      visualPass,
      needsHumanReview,
    },
  };
}
