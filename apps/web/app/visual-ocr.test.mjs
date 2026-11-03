import test from "node:test";
import assert from "node:assert/strict";
import { validateVisualRowTranscription } from "./visual-ocr.ts";

test("accepts a high-confidence visual completion that retains all selectable words in order", () => {
  assert.equal(
    validateVisualRowTranscription(
      "e) Ion-",
      "e) Ion-pump (speed ≥ 300 l/s for N2)",
      "high",
    ),
    "e) Ion-pump (speed ≥ 300 l/s for N2)",
  );
});

test("rejects a transcription that drops selectable source words", () => {
  assert.equal(
    validateVisualRowTranscription("c) Turbo pump with controller", "c) Turbo pump ≥260 l/s", "high"),
    null,
  );
});

test("keeps uncertain visual readings out of the quote text", () => {
  assert.equal(validateVisualRowTranscription("d)", "d) Outgassing station ≥1000°C", "medium"), null);
  assert.equal(validateVisualRowTranscription("d)", "d) Outgassing station ≥1000°C", "low"), null);
});

test("does not create an OCR completion when the image adds no text", () => {
  assert.equal(validateVisualRowTranscription("c) Ion pump", "c) Ion pump", "high"), null);
});

test('rejects changed numeric operators, signs, decimal values and unit case',()=>{
  for(const [source,changed] of [
    ['Capacity ≥ 300 kN','Capacity ≤ 300 kN with controller'],
    ['Temperature -5 °C','Temperature 5 °C with sensor'],
    ['Accuracy ±0.1 mm','Accuracy ±1 mm with gauge'],
    ['Power 5 mW','Power 5 MW with supply'],
  ])assert.equal(validateVisualRowTranscription(source,changed,'high'),null);
  assert.equal(validateVisualRowTranscription('Capacity ≥ 300 kN','Capacity ≥ 300 kN with controller','high'),'Capacity ≥ 300 kN with controller');
});
