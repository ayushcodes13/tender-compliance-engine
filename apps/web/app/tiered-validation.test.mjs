import test from "node:test";
import assert from "node:assert/strict";
import {
  checkVerbatim,
  checkVisual,
  validateCandidateEvidence,
  runTieredValidation,
  normalizeOcrComparable,
  locateOcrQuoteTolerant,
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

test("Tier 1: checkVerbatim strictly rejects number inside another number (500 bar inside 1500 bar)", () => {
  const page = {
    page: 1,
    rawText: "Operating pressure must reach 1500 bar under continuous load.",
  };
  const result = checkVerbatim("500 bar", page);
  assert.equal(result.matched, false);
  assert.equal(result.bbox, null);
});

test("Tier 1: checkVerbatim strictly rejects SI prefix case mismatches (5 MW vs 5 mW)", () => {
  const page = {
    page: 1,
    rawText: "Transmitter output power shall be 5 mW in leveled mode.",
  };
  const result = checkVerbatim("output power shall be 5 MW", page);
  assert.equal(result.matched, false);
  assert.equal(result.bbox, null);
});

test("Tier 2: checkVisual strictly rejects claim when exact sequence is absent despite scattered token presence", () => {
  const page = {
    page: 2,
    rawText: "",
    ocrText: "The output power shall be 200 mW. Calibration reference: 500 mW.",
    ocrPerformed: true,
  };
  const result = checkVisual("The output power shall be 500 mW.", page);
  assert.equal(result.matched, false);
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

test("Tier 2: checkVisual never defaults to high confidence when no spatial region supports it", () => {
  const page = {
    page: 5,
    rawText: "",
    ocrText: "The pump must\ndeliver 200 bar.",
    ocrPerformed: true,
  };

  const result = checkVisual("The pump must deliver 200 bar.", page);
  assert.equal(result.matched, true);
  assert.equal(result.bbox, null);
  assert.notEqual(result.ocrConfidence, "high");
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

test("normalizeOcrComparable reconciles OCR symbol substitutions and bullet glyphs", () => {
  // Dashes
  assert.equal(normalizeOcrComparable("0 — 60 dB"), "0 - 60 db");
  assert.equal(normalizeOcrComparable("0 – 60 dB"), "0 - 60 db");
  assert.equal(normalizeOcrComparable("0 - 60 dB"), "0 - 60 db");

  // Plus-minus
  assert.equal(normalizeOcrComparable("±0.5 dB"), "+0.5 db");
  assert.equal(normalizeOcrComparable("+/- 0.5 dB"), "+ 0.5 db");
  assert.equal(normalizeOcrComparable("200 mW ± 20mW"), "200 mw + 20mw");

  // Bullet artifacts
  assert.equal(normalizeOcrComparable("« Microwave attenuator;"), "microwave attenuator");
  assert.equal(normalizeOcrComparable("• Max output microwave power: 600 mW;"), "max output microwave power 600 mw");
  assert.equal(normalizeOcrComparable("¢ High linearity;"), "high linearity");
});

test("locateOcrQuoteTolerant locates bounding boxes across OCR lines with symbol noise", () => {
  const ocrPositioned = [
    { text: "Microwave Power", box: { x: 80, y: 340, width: 120, height: 15 }, ocrConfidenceLevel: "high" },
    { text: "« Max output microwave power in unleveled mode: 600 mW;", box: { x: 100, y: 360, width: 350, height: 12 }, ocrConfidenceLevel: "high" },
    { text: "Output microwave power in leveled mode: 200 mW + 20mW", box: { x: 100, y: 375, width: 340, height: 12 }, ocrConfidenceLevel: "high" },
    { text: "Microwave power meter;", box: { x: 100, y: 390, width: 150, height: 12 }, ocrConfidenceLevel: "high" },
    { text: "« Microwave attenuator: 0 — 60 dB in 1 dB steps;", box: { x: 100, y: 405, width: 310, height: 12 }, ocrConfidenceLevel: "high" },
    { text: "« Attenuation precision: +0.5 dB;", box: { x: 100, y: 420, width: 220, height: 12 }, ocrConfidenceLevel: "high" },
    { text: "« Automatic phase correction over attenuation range;", box: { x: 100, y: 435, width: 330, height: 12 }, ocrConfidenceLevel: "high" },
  ];

  // 1. Symbol difference: ± vs +
  const matchPlusMinus = locateOcrQuoteTolerant("Output microwave power in leveled mode: 200 mW ± 20mW", ocrPositioned);
  assert.ok(matchPlusMinus);
  assert.equal(matchPlusMinus.bbox.y, 375);
  assert.equal(matchPlusMinus.confidence, "high");

  // 2. Dash difference: en-dash – vs em-dash —
  const matchDash = locateOcrQuoteTolerant("Microwave attenuator: 0 – 60 dB in 1 dB steps;", ocrPositioned);
  assert.ok(matchDash);
  assert.equal(matchDash.bbox.y, 405);

  // 3. Precision ±0.5 dB vs +0.5 dB
  const matchPrecision = locateOcrQuoteTolerant("Attenuation precision: ±0.5 dB;", ocrPositioned);
  assert.ok(matchPrecision);
  assert.equal(matchPrecision.bbox.y, 420);

  // 4. Multi-line window
  const multiLineLines = [
    { text: "Compact system controller mainframe (tower version),", box: { x: 50, y: 100, width: 200, height: 12 }, ocrConfidenceLevel: "high" },
    { text: "including cabling and system power supply.", box: { x: 50, y: 115, width: 180, height: 12 }, ocrConfidenceLevel: "high" },
  ];
  const matchMulti = locateOcrQuoteTolerant("Compact system controller mainframe (tower version), including cabling and system power supply.", multiLineLines);
  assert.ok(matchMulti);
  assert.equal(matchMulti.bbox.y, 100);
  assert.equal(matchMulti.bbox.height, 27);
});

test("Tier 2: checkVisual tolerates OCR symbol noise and assigns bounding box", () => {
  const page = {
    page: 2,
    rawText: "",
    ocrText: "« Attenuation precision: +0.5 dB;\n« Microwave attenuator: 0 — 60 dB in 1 dB steps;",
    ocrPositioned: [
      { text: "« Attenuation precision: +0.5 dB;", box: { x: 100, y: 420, width: 220, height: 12 }, ocrConfidenceLevel: "high" },
      { text: "« Microwave attenuator: 0 — 60 dB in 1 dB steps;", box: { x: 100, y: 405, width: 310, height: 12 }, ocrConfidenceLevel: "high" },
    ],
    ocrPerformed: true,
  };

  const result1 = checkVisual("Attenuation precision: ±0.5 dB;", page);
  assert.equal(result1.matched, true);
  assert.ok(result1.bbox);
  assert.equal(result1.bbox.y, 420);

  const result2 = checkVisual("Microwave attenuator: 0 – 60 dB in 1 dB steps;", page);
  assert.equal(result2.matched, true);
  assert.ok(result2.bbox);
  assert.equal(result2.bbox.y, 405);
});
