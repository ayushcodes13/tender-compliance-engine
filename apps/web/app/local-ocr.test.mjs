import test from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildOcrTextPositionMap, combineOcrConfidence, createPopplerPageRenderer, parseTesseractTsv, recognizePageImage, resolveTesseractLanguage } from "./local-ocr.ts";

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
    confidence: 90,
    confidenceLevel: "high",
    words: [
      { start: 0, end: 3, text: "100", bbox: { x: 40, y: 80, width: 60, height: 20 }, confidence: 96, confidenceLevel: "high" },
      { start: 4, end: 6, text: "kN", bbox: { x: 110, y: 80, width: 40, height: 20 }, confidence: 90, confidenceLevel: "high" },
    ],
  });
  assert.equal(result.lines[0].confidenceLevel, "low");
});

test("low-confidence numeric and adjacent unit tokens cannot be hidden by a high word average", () => {
  const labels = ["Maximum", "operating", "pressure", "value", "confidence", "level", "remains", "quite", "high"];
  const values = [...labels.map((text) => ({ text, confidence: 98 })), { text: "5", confidence: 5 }, { text: "%", confidence: 96 }];
  const tsv = [
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    ...values.map((word, index) => `5\t1\t1\t1\t1\t${index + 1}\t${index * 50}\t10\t40\t10\t${word.confidence}\t${word.text}`),
  ].join("\n");
  const [line] = parseTesseractTsv(tsv, { width: 700, height: 100 }, { width: 700, height: 100 }).lines;
  assert.equal(line.confidence, 5, "the critical numeric token controls the line confidence");
  assert.equal(line.confidenceLevel, "low", "the numeric token controls technical-value confidence");
  assert.equal(line.words.find((word) => word.text === "5").confidenceLevel, "low");
  assert.equal(line.words.find((word) => word.text === "%").confidenceLevel, "high");

  const weakUnit = values.map((word) => ({ ...word, confidence: word.text === "%" ? 5 : 98 }));
  const unitTsv = [
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    ...weakUnit.map((word, index) => `5\t1\t1\t1\t1\t${index + 1}\t${index * 50}\t10\t40\t10\t${word.confidence}\t${word.text}`),
  ].join("\n");
  const [unitLine] = parseTesseractTsv(unitTsv, { width: 700, height: 100 }, { width: 700, height: 100 }).lines;
  assert.equal(unitLine.confidence, 5, "the unit adjacent to a technical value also affects confidence");
  assert.equal(unitLine.confidenceLevel, "low");
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
    { text: "First row", bbox: { x: 10, y: 20, width: 40, height: 8 }, confidence: 91, confidenceLevel: "high", words: [] },
    { text: "Second row", bbox: { x: 10, y: 32, width: 45, height: 8 }, confidence: 70, confidenceLevel: "medium", words: [] },
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

test("aborting Tesseract recognition terminates its process and cleans temporary input", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tce-test-tesseract-cancel-"));
  const binary = join(directory, "slow-tesseract");
  await writeFile(binary, "#!/usr/bin/env node\nsetInterval(() => {}, 1000);\n", { mode: 0o700 });
  await chmod(binary, 0o700);
  const controller = new AbortController();
  try {
    const pendingRecognition = recognizePageImage({
      image: new Uint8Array([1, 2, 3]),
      imageSize: { width: 1, height: 1 },
      pageSize: { width: 1, height: 1 },
      binary,
      signal: controller.signal,
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    controller.abort("cancel test OCR");
    await assert.rejects(pendingRecognition, { name: "AbortError" });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
