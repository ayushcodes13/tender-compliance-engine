import test from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildOcrTextPositionMap, combineOcrConfidence, createPopplerPageRenderer, parseTesseractTsv, resolveTesseractLanguage } from "./local-ocr.ts";

test("parses OCR words into source-ordered lines with page-coordinate boxes", () => {
  const tsv = [
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    "5\t1\t1\t1\t2\t1\t20\t40\t30\t10\t96\t100",
    "5\t1\t1\t1\t2\t2\t55\t40\t20\t10\t90\tkN",
    "5\t1\t1\t1\t1\t1\t10\t12\t40\t8\t55\tMaximum",
    "5\t1\t1\t1\t1\t2\t60\t12\t30\t8\t-1\t",
  ].join("\n");

  const result = parseTesseractTsv(tsv, { width: 300, height: 600 }, { width: 150, height: 300 });
  assert.equal(result.text, "Maximum\n100 kN");
  assert.deepEqual(result.lines[1], {
    text: "100 kN",
    bbox: { x: 40, y: 80, width: 110, height: 20 },
    confidence: 93,
    confidenceLevel: "high",
  });
  assert.equal(result.lines[0].confidenceLevel, "low");
});

test("returns empty OCR text for malformed TSV or invalid image dimensions", () => {
  assert.deepEqual(parseTesseractTsv("not tsv", { width: 100, height: 100 }, { width: 100, height: 100 }), { text: "", lines: [] });
  assert.deepEqual(parseTesseractTsv("header", { width: 100, height: 100 }, { width: 0, height: 100 }), { text: "", lines: [] });
});

test("combines line confidence conservatively for multi-line quotations", () => {
  assert.equal(combineOcrConfidence(["high", "high"]), "high");
  assert.equal(combineOcrConfidence(["high", "medium"]), "medium");
  assert.equal(combineOcrConfidence(["high", "low"]), "low");
  assert.equal(combineOcrConfidence([]), null);
});

test("allows configured Tesseract languages without shell interpretation", () => {
  assert.equal(resolveTesseractLanguage("eng+hin"), "eng+hin");
  assert.equal(resolveTesseractLanguage("eng; rm -rf"), "eng");
  assert.equal(resolveTesseractLanguage(""), "eng");
});

test("maps each OCR line to its approximate source box without mapping inserted line breaks", () => {
  const lines = [
    { text: "First row", bbox: { x: 10, y: 20, width: 40, height: 8 }, confidence: 91, confidenceLevel: "high" },
    { text: "Second row", bbox: { x: 10, y: 32, width: 45, height: 8 }, confidence: 70, confidenceLevel: "medium" },
  ];
  const result = buildOcrTextPositionMap(lines);

  assert.equal(result.text, "First row\nSecond row");
  assert.equal(result.rawItemMap[9], -1);
  assert.equal(result.rawItemMap[10], 1);
  assert.deepEqual(result.positioned.map((line) => [line.start, line.end, line.text, line.box, line.ocrConfidenceLevel]), [
    [0, 9, "First row", lines[0].bbox, "high"],
    [10, 20, "Second row", lines[1].bbox, "medium"],
  ]);
});

test("aborting a Poppler render terminates its process and leaves renderer cleanup available", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tce-test-poppler-cancel-"));
  const binary = join(directory, "slow-renderer");
  await writeFile(binary, "#!/usr/bin/env node\nsetInterval(() => {}, 1000);\n", { mode: 0o700 });
  await chmod(binary, 0o700);
  const renderer = createPopplerPageRenderer(new Uint8Array([0x25, 0x50, 0x44, 0x46]), binary);
  const controller = new AbortController();
  try {
    const pendingRender = renderer.renderPage(1, 1700, controller.signal);
    await new Promise((resolve) => setTimeout(resolve, 100));
    controller.abort("cancel test render");
    await assert.rejects(pendingRender, { name: "AbortError" });
  } finally {
    await renderer.close();
    await rm(directory, { recursive: true, force: true });
  }
});
