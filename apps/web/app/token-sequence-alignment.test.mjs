import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeToken,
  levenshteinDistance,
  tokenSimilarity,
  tokenizeText,
  alignTokenSequence,
  locateQuoteSequenceAlignment,
  hasSemanticAgreement,
} from "./token-sequence-alignment.ts";

test("normalizeToken reconciles typographic variations and punctuation", () => {
  assert.equal(normalizeToken("0—60"), "0-60");
  assert.equal(normalizeToken("0–60"), "0-60");
  assert.equal(normalizeToken("±0.5dB"), "+0.5db");
  assert.equal(normalizeToken("+/-0.5"), "+0.5");
  assert.equal(normalizeToken("«Microwave;"), "microwave");
  assert.equal(normalizeToken("•Power:"), "power");
  assert.equal(normalizeToken("(128,000)"), "128,000");
});

test("levenshteinDistance calculates correct edit distance", () => {
  assert.equal(levenshteinDistance("kitten", "sitting"), 3);
  assert.equal(levenshteinDistance("flaw", "lawn"), 2);
  assert.equal(levenshteinDistance("same", "same"), 0);
  assert.equal(levenshteinDistance("", "abc"), 3);
});

test("tokenSimilarity scores matching and near-matching tokens", () => {
  assert.equal(tokenSimilarity("microwave", "microwave"), 1.0);
  // Short tokens require exact match to avoid false positive
  assert.equal(tokenSimilarity("10", "11"), 0.0);
  assert.equal(tokenSimilarity("db", "gb"), 0.0);
  // Longer tokens with 1 typo match with high similarity
  assert.ok(tokenSimilarity("attenuator", "attenuater") >= 0.85);
  // Completely different tokens return 0
  assert.equal(tokenSimilarity("attenuator", "spectrometer"), 0.0);
});

test("tokenizeText produces spatially-bound tokens with exact offsets", () => {
  const text = "Max output: 600 mW;";
  const tokens = tokenizeText(text);
  assert.equal(tokens.length, 4);
  assert.equal(tokens[0].raw, "Max");
  assert.equal(tokens[0].norm, "max");
  assert.equal(tokens[0].start, 0);
  assert.equal(tokens[0].end, 3);

  assert.equal(tokens[2].raw, "600");
  assert.equal(tokens[2].norm, "600");

  assert.equal(tokens[3].raw, "mW;");
  assert.equal(tokens[3].norm, "mw");
});

test("alignTokenSequence matches queries with OCR symbol differences", () => {
  const doc = "Tender Section. Output microwave power in leveled mode: 200 mW + 20mW for testing.";
  const query = "Output microwave power in leveled mode: 200 mW ± 20mW";

  const match = alignTokenSequence(query, doc);
  assert.ok(match);
  assert.ok(match.score >= 0.90);
  const matchedText = doc.slice(match.startOffset, match.endOffset);
  assert.equal(matchedText, "Output microwave power in leveled mode: 200 mW + 20mW");
});

test("alignTokenSequence matches queries with dash differences", () => {
  const doc = "Specifications:\n« Microwave attenuator: 0 — 60 dB in 1 dB steps;\nNext line.";
  const query = "• Microwave attenuator: 0 – 60 dB in 1 dB steps;";

  const match = alignTokenSequence(query, doc);
  assert.ok(match);
  assert.ok(match.score >= 0.90);
  const matchedText = doc.slice(match.startOffset, match.endOffset);
  assert.equal(matchedText, "Microwave attenuator: 0 — 60 dB in 1 dB steps;");
});

test("alignTokenSequence rejects hallucinations and ungrounded clauses", () => {
  const doc = "High Sensitivity CW-EPR Resonator with microwave bridge.";
  const hallucination = "Quantum entanglement generator with cryogenic vacuum chamber";

  const match = alignTokenSequence(hallucination, doc);
  assert.equal(match, null);
});

test("ADVERSARIAL: alignTokenSequence rejects changed numerical values despite high similarity", () => {
  // Case 1: 500 bar vs 200 bar (0.90 lexical overlap)
  const doc1 = "The hydraulic test pressure must be at least 200 bar under continuous load.";
  const claim1 = "The hydraulic test pressure must be at least 500 bar under continuous load.";
  assert.equal(alignTokenSequence(claim1, doc1), null, "Rejects 500 bar vs 200 bar");

  // Case 2: 500 RPM vs 200 RPM (0.91 lexical overlap)
  const doc2 = "The high speed motor operates at 200 RPM during standard cycle.";
  const claim2 = "The high speed motor operates at 500 RPM during standard cycle.";
  assert.equal(alignTokenSequence(claim2, doc2), null, "Rejects 500 RPM vs 200 RPM");

  // Case 3: 10 GHz vs 18 GHz
  const doc3 = "Microwave bridge center frequency: 10 GHz with low noise Gunn diode.";
  const claim3 = "Microwave bridge center frequency: 18 GHz with low noise Gunn diode.";
  assert.equal(alignTokenSequence(claim3, doc3), null, "Rejects 18 GHz vs 10 GHz");
});

test("ADVERSARIAL: alignTokenSequence rejects conflicting directional operators", () => {
  // Case 1: minimum vs maximum
  const doc1 = "The automated sample carousel capacity: Maximum 10 samples per carousel.";
  const claim1 = "The automated sample carousel capacity: Minimum 10 samples per carousel.";
  assert.equal(alignTokenSequence(claim1, doc1), null, "Rejects Minimum vs Maximum");

  // Case 2: at least vs at most
  const doc2 = "Operating duration shall be at most 24 hours without maintenance.";
  const claim2 = "Operating duration shall be at least 24 hours without maintenance.";
  assert.equal(alignTokenSequence(claim2, doc2), null, "Rejects at least vs at most");
});

test("ADVERSARIAL: alignTokenSequence rejects conflicting negation polarity", () => {
  const doc1 = "The spectrometer shall be supplied with external closed-loop chiller.";
  const claim1 = "The spectrometer shall be supplied without external closed-loop chiller.";
  assert.equal(alignTokenSequence(claim1, doc1), null, "Rejects without vs with");
});

test("ADVERSARIAL: alignTokenSequence rejects mismatched technical units", () => {
  const doc1 = "Maximum laser output: 500 mW in continuous wave mode.";
  const claim1 = "Maximum laser output: 500 bar in continuous wave mode.";
  assert.equal(alignTokenSequence(claim1, doc1), null, "Rejects 500 bar vs 500 mW");
});

test("locateQuoteSequenceAlignment calculates exact multi-line bounding boxes", () => {
  const lines = [
    "Line 1: Header information",
    "Line 2: Compact system controller mainframe (tower version),",
    "Line 3: including cabling and system power supply and Ethernet.",
    "Line 4: Footer information",
  ];

  let rawText = "";
  const rawItemMap = [];
  const positioned = [];

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const start = rawText.length;
    rawText += line + "\n";
    const end = rawText.length;
    for (let o = start; o < end; o += 1) rawItemMap[o] = i;
    positioned.push({
      start,
      end,
      box: { x: 50, y: 100 + i * 25, width: 300, height: 18 },
    });
  }

  const query = "Compact system controller mainframe (tower version), including cabling and system power supply";
  const box = locateQuoteSequenceAlignment(query, rawText, rawItemMap, positioned);

  assert.ok(box);
  assert.equal(box.x, 50);
  assert.equal(box.y, 125); // Starts at line index 1 (y = 125)
  assert.equal(box.height, 43); // Spans line index 1 and 2 (height = (150+18) - 125 = 43)
});
