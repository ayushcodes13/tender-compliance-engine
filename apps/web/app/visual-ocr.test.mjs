import test from "node:test";
import assert from "node:assert/strict";
import { separateVisualCompletionProposal, validateVisualCompletionProposal } from "./visual-ocr.ts";

test("keeps a high-confidence visual completion as a separate unverified proposal", () => {
  const result = separateVisualCompletionProposal(
    "e) Ion-",
    "e) Ion-pump (speed ≥ 300 l/s for N2)",
    "high",
  );
  assert.equal(result.sourceQuote, "e) Ion-");
  assert.equal(result.unverifiedSuggestion, "e) Ion-pump (speed ≥ 300 l/s for N2)");
});

test("suggestions must retain every selectable source token in order", () => {
  assert.equal(
    validateVisualCompletionProposal(
      "e) Ion-",
      "e) Ion-pump (speed ≥ 300 l/s for N2)",
      "high",
    ),
    "e) Ion-pump (speed ≥ 300 l/s for N2)",
  );
});

test("rejects a transcription that drops selectable source words", () => {
  assert.equal(
    validateVisualCompletionProposal("c) Turbo pump with controller", "c) Turbo pump ≥260 l/s", "high"),
    null,
  );
});

test("keeps uncertain visual readings out of the quote text", () => {
  assert.equal(validateVisualCompletionProposal("d)", "d) Outgassing station ≥1000°C", "medium"), null);
  assert.equal(validateVisualCompletionProposal("d)", "d) Outgassing station ≥1000°C", "low"), null);
});

test("does not create an OCR completion when the image adds no text", () => {
  assert.equal(validateVisualCompletionProposal("c) Ion pump", "c) Ion pump", "high"), null);
});

test('rejects changed numeric operators, signs, decimal values and unit case',()=>{
  for(const [source,changed] of [
    ['Capacity ≥ 300 kN','Capacity ≤ 300 kN with controller'],
    ['Temperature -5 °C','Temperature 5 °C with sensor'],
    ['Accuracy ±0.1 mm','Accuracy ±1 mm with gauge'],
    ['Power 5 mW','Power 5 MW with supply'],
  ])assert.equal(validateVisualCompletionProposal(source,changed,'high'),null);
  assert.equal(validateVisualCompletionProposal('Capacity ≥ 300 kN','Capacity ≥ 300 kN with controller','high'),'Capacity ≥ 300 kN with controller');
});

test("keeps unsupported model additions out of source text for the audit reproductions", () => {
  for (const [source, suggestion] of [
    ["Pump shall deliver 200 bar", "Pump shall deliver 200 bar and be compatible with ISO 9001"],
    ["PLC controller shall be included", "PLC controller shall be included and warranty shall be 10 years"],
    ["Pressure 200 bar", "Pressure ≥ 200 bar"],
  ]) {
    const result = separateVisualCompletionProposal(source, suggestion, "high");
    assert.equal(result.sourceQuote, source);
    assert.equal(result.unverifiedSuggestion, suggestion);
  }
});
