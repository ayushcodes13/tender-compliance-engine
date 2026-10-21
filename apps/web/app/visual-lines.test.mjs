import test from "node:test";
import assert from "node:assert/strict";
import { displayLinesForQuote } from "./visual-lines.ts";

function source(text, pieces) {
  let rawText = "";
  const rawItemMap = [];
  const positioned = [];
  for (const [index, piece] of pieces.entries()) {
    if (index > 0) {
      rawText += " ";
      rawItemMap.push(-1);
    }
    const start = rawText.length;
    rawText += piece.text;
    for (let i = start; i < rawText.length; i += 1) rawItemMap.push(index);
    positioned.push({
      start,
      end: rawText.length,
      text: piece.text,
      pdfX: piece.x,
      pdfY: piece.y,
      pdfWidth: piece.width,
      pdfHeight: 10,
    });
  }
  assert.equal(rawText.replace(/\s+/g, " ").trim(), text.replace(/\s+/g, " ").trim());
  return { rawText, rawItemMap, positioned };
}

test("reconstructs split hyphenated words without inserting artificial spaces", () => {
  const sample = source("non- magnetic", [
    { text: "non-", x: 10, y: 100, width: 22 },
    { text: "magnetic", x: 32, y: 100, width: 38 },
  ]);

  assert.deepEqual(displayLinesForQuote("non- magnetic", sample.rawText, sample.rawItemMap, sample.positioned), ["non-magnetic"]);
});

test("preserves explicit word spaces and source line breaks", () => {
  const sample = source("The software works\nwithin the system", [
    { text: "The software works", x: 10, y: 100, width: 94 },
    { text: "within the system", x: 10, y: 88, width: 88 },
  ]);

  assert.deepEqual(displayLinesForQuote("The software works within the system", sample.rawText, sample.rawItemMap, sample.positioned), [
    "The software works",
    "within the system",
  ]);
});

test("does not reconstruct text when the quote is ambiguous", () => {
  const sample = source("same line same line", [
    { text: "same line", x: 10, y: 100, width: 40 },
    { text: "same line", x: 50, y: 100, width: 40 },
  ]);

  assert.equal(displayLinesForQuote("same line", sample.rawText, sample.rawItemMap, sample.positioned), null);
});
