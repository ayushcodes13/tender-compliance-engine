import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeToken,
  tokenSimilarity,
  tokenizeText,
  alignExactTokenSequence,
  alignTokenSequence,
  locateQuoteSequenceAlignment,
  findUniqueTokenBoundedMatch,
  hasTechnicalAgreement,
} from "./token-sequence-alignment.ts";

test("normalizeToken reconciles typographic variations while preserving signs, units, and tolerances", () => {
  assert.equal(normalizeToken("0—60"), "0-60");
  assert.equal(normalizeToken("0–60"), "0-60");
  assert.equal(normalizeToken("±0.5dB"), "±0.5dB");
  assert.equal(normalizeToken("+/-0.5"), "±0.5");
  assert.equal(normalizeToken("-20°C"), "-20°C");
  assert.equal(normalizeToken("«Microwave;"), "microwave");
  assert.equal(normalizeToken("•Power:"), "power");
  assert.equal(normalizeToken("(128,000)"), "128,000");
  // Case sensitive SI units preserved
  assert.equal(normalizeToken("MW"), "MW");
  assert.equal(normalizeToken("mW"), "mW");
  assert.equal(normalizeToken("MA"), "MA");
  assert.equal(normalizeToken("mA"), "mA");
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
  assert.equal(tokens[3].norm, "mW");
});

test("alignExactTokenSequence matches queries across line breaks and OCR symbol differences", () => {
  const doc = "Tender Section. Output microwave power\nin leveled mode: 200 mW +/- 20mW for testing.";
  const query = "Output microwave power in leveled mode: 200 mW ± 20mW";

  const match = alignExactTokenSequence(query, doc);
  assert.ok(match);
  assert.equal(match.score, 1.0);
  const matchedText = doc.slice(match.startOffset, match.endOffset);
  assert.equal(matchedText, "Output microwave power\nin leveled mode: 200 mW +/- 20mW");
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

test("P0: strictly rejects SI prefix case mismatches (MW vs mW, MA vs mA)", () => {
  const docMW = "Transmitter output power 5 mW in leveled mode.";
  const claimMW = "Transmitter output power 5 MW in leveled mode.";
  assert.equal(alignExactTokenSequence(claimMW, docMW), null);
  assert.equal(findUniqueTokenBoundedMatch(docMW, claimMW), null);

  const docMA = "Maximum operating current: 20 mA at 24V.";
  const claimMA = "Maximum operating current: 20 MA at 24V.";
  assert.equal(alignExactTokenSequence(claimMA, docMA), null);
  assert.equal(findUniqueTokenBoundedMatch(docMA, claimMA), null);
});

test("P0: strictly rejects signed number differences (-20 vs 20)", () => {
  const doc = "Temperature operating range: -20 °C to +50 °C.";
  const claim = "Temperature operating range: 20 °C to +50 °C.";
  assert.equal(alignExactTokenSequence(claim, doc), null);
  assert.equal(findUniqueTokenBoundedMatch(doc, claim), null);
});

test("P0: strictly rejects tolerance operator mismatch (±5% vs +5%)", () => {
  const doc = "Frequency stability tolerance: ±5% under load.";
  const claim = "Frequency stability tolerance: +5% under load.";
  assert.equal(alignExactTokenSequence(claim, doc), null);
  assert.equal(findUniqueTokenBoundedMatch(doc, claim), null);
});

test("P0: strictly rejects number inside another number (500 bar inside 1500 bar)", () => {
  const doc = "The hydraulic test pressure must be 1500 bar under continuous load.";
  const claim = "500 bar";
  assert.equal(findUniqueTokenBoundedMatch(doc, claim), null);
});

test("P1: declines overlapping repeated passages with requireUnique: true (pump pump in pump pump pump)", () => {
  const doc = "pump pump pump";
  const claim = "pump pump";
  assert.equal(alignExactTokenSequence(claim, doc, { requireUnique: true }), null);
  assert.equal(findUniqueTokenBoundedMatch(doc, claim), null);
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
