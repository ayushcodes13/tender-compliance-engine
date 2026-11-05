import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeToken,
  tokenSimilarity,
  tokenizeText,
  alignExactTokenSequence,
  alignTokenSequence,
  locateQuoteSequenceAlignment,
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

test("tokenSimilarity enforces strict binary token equality without fuzzy thresholds", () => {
  assert.equal(tokenSimilarity("microwave", "microwave"), 1.0);
  assert.equal(tokenSimilarity("10", "11"), 0.0);
  assert.equal(tokenSimilarity("db", "gb"), 0.0);
  // Zero fuzzy matching: even a 1-character typo returns 0.0
  assert.equal(tokenSimilarity("attenuator", "attenuater"), 0.0);
  assert.equal(tokenSimilarity("500", "200"), 0.0);
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

test("alignExactTokenSequence matches queries across line breaks and OCR symbol differences", () => {
  const doc = "Tender Section. Output microwave power\nin leveled mode: 200 mW + 20mW for testing.";
  const query = "Output microwave power in leveled mode: 200 mW ± 20mW";

  const match = alignExactTokenSequence(query, doc);
  assert.ok(match);
  assert.equal(match.score, 1.0);
  const matchedText = doc.slice(match.startOffset, match.endOffset);
  assert.equal(matchedText, "Output microwave power\nin leveled mode: 200 mW + 20mW");
});

test("alignExactTokenSequence matches queries with dash differences", () => {
  const doc = "Specifications:\n« Microwave attenuator: 0 — 60 dB in 1 dB steps;\nNext line.";
  const query = "• Microwave attenuator: 0 – 60 dB in 1 dB steps;";

  const match = alignExactTokenSequence(query, doc);
  assert.ok(match);
  assert.equal(match.score, 1.0);
  const matchedText = doc.slice(match.startOffset, match.endOffset);
  assert.equal(matchedText, "Microwave attenuator: 0 — 60 dB in 1 dB steps;");
});

test("alignExactTokenSequence strictly rejects altered numbers", () => {
  const doc1 = "The hydraulic test pressure must be at least 200 bar under continuous load.";
  const claim1 = "The hydraulic test pressure must be at least 500 bar under continuous load.";
  assert.equal(alignExactTokenSequence(claim1, doc1), null);

  const doc2 = "The high speed motor operates at 200 RPM during standard cycle.";
  const claim2 = "The high speed motor operates at 500 RPM during standard cycle.";
  assert.equal(alignExactTokenSequence(claim2, doc2), null);
});

test("alignExactTokenSequence strictly rejects conflicting directional operators", () => {
  const doc1 = "The automated sample carousel capacity: Maximum 10 samples per carousel.";
  const claim1 = "The automated sample carousel capacity: Minimum 10 samples per carousel.";
  assert.equal(alignExactTokenSequence(claim1, doc1), null);
});

test("alignExactTokenSequence strictly rejects altered words and typos", () => {
  const doc1 = "Automatic phase correction over attenuation range;";
  const claim1 = "Automatic phase correction over attenuater range;";
  assert.equal(alignExactTokenSequence(claim1, doc1), null);
});

test("alignExactTokenSequence strictly rejects hallucinations", () => {
  const doc = "High Sensitivity CW-EPR Resonator with microwave bridge.";
  const hallucination = "Quantum entanglement generator with cryogenic vacuum chamber";
  assert.equal(alignExactTokenSequence(hallucination, doc), null);
});

test("alignExactTokenSequence declines ambiguous repeated passages on the same page when requireUnique is set", () => {
  const doc = "Item 1: Quantity: 1 EA with standard warranty.\nItem 2: Quantity: 1 EA with standard warranty.";
  const query = "Quantity: 1 EA";
  // With requireUnique: true, duplicate occurrences must return null to avoid ambiguous/wrong-row highlighting
  assert.equal(alignExactTokenSequence(query, doc, { requireUnique: true }), null);
  // Without requireUnique, returns the first occurrence
  assert.ok(alignExactTokenSequence(query, doc, { requireUnique: false }));
});

test("locateQuoteSequenceAlignment calculates exact multi-line bounding boxes", () => {
  const lines = [
    "Header information",
    "Compact system controller mainframe (tower version),",
    "including cabling and system power supply and Ethernet.",
    "Footer information",
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
  assert.equal(box.y, 125);
  assert.equal(box.height, 43);
});
