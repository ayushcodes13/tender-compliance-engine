import test from "node:test";
import assert from "node:assert/strict";
import {
  checkVerbatim,
  checkVisual,
  validateCandidateEvidence,
  runTieredValidation,
} from "./tiered-validation.ts";

test("Tier 1: checkVerbatim passes on exact matching native text and derives bounding box", () => {
  const page = {
    page: 1,
    rawText: "The microwave bridge shall operate in X-band with low noise.",
    rawItemMap: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    positioned: [
      { start: 0, end: 20, box: { x: 10, y: 50, width: 100, height: 12 } },
      { start: 21, end: 60, box: { x: 115, y: 50, width: 200, height: 12 } },
    ],
  };

  const result = checkVerbatim("microwave bridge shall operate in X-band", page);
  assert.equal(result.matched, true);
  assert.ok(result.bbox);
  assert.equal(result.bbox.x, 10);
  assert.equal(result.bbox.y, 50);
});

test("Tier 1: checkVerbatim fails when quote is not in native rawText", () => {
  const page = {
    page: 1,
    rawText: "Console specifications.",
  };
  const result = checkVerbatim("microwave bridge", page);
  assert.equal(result.matched, false);
  assert.equal(result.bbox, null);
});

test("Tier 2: checkVisual passes on OCR text when native text is missing", () => {
  const page = {
    page: 2,
    rawText: "", // scanned page, no native text
    ocrText: "Automatic Frequency Control (AFC) with locking range +/- 50 MHz.",
    ocrPositioned: [
      {
        start: 0,
        end: 64,
        box: { x: 20, y: 100, width: 300, height: 15 },
        ocrConfidenceLevel: "high",
      },
    ],
    ocrPerformed: true,
  };

  const result = checkVisual("Automatic Frequency Control (AFC)", page);
  assert.equal(result.matched, true);
  assert.ok(result.bbox);
  assert.equal(result.ocrConfidence, "high");
});

test("Tier 2: checkVisual handles OCR token noise like sl vs sil", () => {
  const page = {
    page: 3,
    rawText: "",
    ocrText: "1. sil. no. frequency stability 10^-9 per day",
    ocrPerformed: true,
  };

  const result = checkVisual("sl. no. frequency stability", page);
  assert.equal(result.matched, true);
});

test("Tier 3: falls back to needs_human_review when text fails verbatim and visual checks", () => {
  const page = {
    page: 4,
    rawText: "Unrelated section text.",
    ocrText: "Unrelated ocr text.",
    ocrPerformed: true,
  };

  const candidate = {
    id: "req-unverified",
    quote: "Invented non-existent parameter 999 GHz",
    page: 4,
  };

  const validated = validateCandidateEvidence(candidate, page);
  assert.equal(validated.verdict, "needs_human_review");
  assert.equal(validated.precision, "unverified");
  assert.equal(validated.needsHumanReview, true);
  assert.equal(validated.method, "unverified");
  assert.ok(validated.unverifiedReason?.includes("marked for human review"));
});

test("runTieredValidation validates all candidates and aggregates summary", () => {
  const pages = [
    {
      page: 1,
      rawText: "Microwave Bridge operates at 9.8 GHz.",
    },
    {
      page: 2,
      rawText: "",
      ocrText: "Digital Signal Processing Unit with 1 GS/s sampling.",
      ocrPerformed: true,
    },
    {
      page: 3,
      rawText: "Header information only.",
      ocrText: "Header information only.",
      ocrPerformed: true,
    },
  ];

  const candidates = [
    { id: "c1", quote: "Microwave Bridge operates", page: 1 },
    { id: "c2", quote: "Digital Signal Processing Unit", page: 2 },
    { id: "c3", quote: "Cryostat helium retention 100 days", page: 3 },
  ];

  const { results, summary } = runTieredValidation(candidates, pages);
  assert.equal(summary.total, 3);
  assert.equal(summary.verbatimPass, 1);
  assert.equal(summary.visualPass, 1);
  assert.equal(summary.needsHumanReview, 1);

  assert.equal(results.get("c1")?.verdict, "verbatim_pass");
  assert.equal(results.get("c2")?.verdict, "visual_pass");
  assert.equal(results.get("c3")?.verdict, "needs_human_review");
  assert.equal(results.get("c3")?.needsHumanReview, true);
});
