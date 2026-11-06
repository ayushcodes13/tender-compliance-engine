import test from "node:test";
import assert from "node:assert/strict";
import {
  buildRequirementSourceReference,
  buildSourcePageModel,
  createSourceDocumentModel,
  findUniqueSourceText,
} from "./source-document.ts";

test("creates a stable document fingerprint and a distinct version identity", () => {
  const first = createSourceDocumentModel(new Uint8Array([1, 2, 3]), 2);
  const same = createSourceDocumentModel(new Uint8Array([1, 2, 3]), 2);
  const changed = createSourceDocumentModel(new Uint8Array([1, 2, 4]), 2);
  assert.equal(first.fingerprint, same.fingerprint);
  assert.equal(first.documentId, same.documentId);
  assert.notEqual(first.fingerprint, changed.fingerprint);
  assert.equal(first.documentVersionId, `ver-${first.fingerprint}`);
  assert.equal(first.pageCount, 2);
});

test("preserves physical page text blocks with offsets, geometry, and source table cells", () => {
  const document = createSourceDocumentModel(new Uint8Array([7]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 3,
    width: 600,
    height: 800,
    sourceText: "Machine\n≥ 300 kN",
    positionedItems: [
      { start: 0, end: 7, text: "Machine", box: { x: 10, y: 20, width: 40, height: 8 } },
      { start: 8, end: 16, text: "≥ 300 kN", box: { x: 60, y: 20, width: 50, height: 8 } },
    ],
    vectorRows: [{ cells: ["Machine", "≥ 300 kN"], cellBoxes: [
      { x: 5, y: 10, width: 45, height: 15 }, { x: 50, y: 10, width: 70, height: 15 },
    ] }],
  });
  assert.equal(page.physicalPdfPageNumber, 3);
  assert.equal(page.printedPageNumber, undefined);
  assert.equal(page.coordinateSystem, "pdfjs-viewport-scale-1");
  assert.deepEqual(page.textBlocks.map((block) => [block.text, block.startOffset, block.endOffset]), [
    ["Machine", 0, 7], ["≥ 300 kN", 8, 16],
  ]);
  assert.equal(page.tables[0].rows[0].cells[1].sourceText, "≥ 300 kN");
  assert.equal(page.tables[0].rows[0].cells[1].bbox.x, 50);
});

test("matches normalized whitespace while keeping original source offsets and rejecting duplicate text", () => {
  const source = "Header\n  Range   ≥ 300 kN\nFooter";
  const match = findUniqueSourceText(source, "Range ≥ 300 kN");
  assert.ok(match);
  assert.equal(match.sourceText, "Range   ≥ 300 kN");
  assert.equal(source.slice(match.startOffset, match.endOffset), match.sourceText);
  assert.equal(findUniqueSourceText("Repeated\nRepeated", "Repeated"), null);
});

test("native references include exact quote offsets and source cell identity when known", () => {
  const document = createSourceDocumentModel(new Uint8Array([9]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 8,
    width: 300,
    height: 400,
    sourceText: "Parameter   Required\nForce   ≥ 300 kN",
    positionedItems: [],
    vectorRows: [{ cells: ["Force", "≥ 300 kN"], cellBoxes: [null, { x: 100, y: 30, width: 80, height: 12 }] }],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "≥ 300 kN", bbox: { x: 100, y: 30, width: 80, height: 12 },
    sourceCellLocation: { rowIndex: 0, columnIndex: 1 },
  });
  assert.equal(reference.physicalPdfPageNumber, 8);
  assert.equal(reference.locationPrecision, "exact");
  assert.equal(reference.sourceText, "≥ 300 kN");
  assert.equal(reference.documentFingerprint, document.fingerprint);
  assert.equal(reference.offsetUnit, "utf16-code-unit");
  assert.equal(reference.offsetScope, "page-source-text");
  assert.equal(reference.bboxCoordinateSystem, "pdfjs-viewport-scale-1");
  assert.equal(reference.sourceCell?.columnIndex, 1);
  assert.equal(reference.sourceCell?.rowId, page.tables[0].rows[0].id);
  assert.equal(reference.startOffset, 29);
  assert.equal(reference.endOffset, 37);
});

test("visual transcriptions keep OCR text separate from native context and omit invented offsets", () => {
  const document = createSourceDocumentModel(new Uint8Array([4]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 1, width: 100, height: 200,
    sourceText: "Capacity", positionedItems: [],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "Capacity ≥ 300 kN", bbox: { x: 1, y: 2, width: 30, height: 4 },
    visualTranscription: "Capacity ≥ 300 kN", selectableTextContext: "Capacity",
    ocrConfidence: "high",
  });
  assert.equal(reference.extractionMethod, "visual-transcription");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.sourceText, "Capacity");
  assert.equal(reference.transcribedText, "Capacity ≥ 300 kN");
  assert.equal(reference.ocrConfidence, "high");
  assert.equal("startOffset" in reference, false);
  assert.equal("endOffset" in reference, false);
});

test("stores local OCR regions separately from native text with approximate citations", () => {
  const document = createSourceDocumentModel(new Uint8Array([6]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 2, width: 200, height: 300,
    sourceText: "", positionedItems: [],
    ocrRegions: [{
      text: "Load capacity ≥ 300 kN",
      bbox: { x: 20, y: 40, width: 100, height: 12 },
      confidence: 78,
      confidenceLevel: "medium",
    }],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "Load capacity ≥ 300 kN", bbox: { x: 20, y: 40, width: 100, height: 12 },
    visualTranscription: "Load capacity ≥ 300 kN", transcriptionMethod: "tesseract-ocr", ocrConfidence: "medium",
  });

  assert.equal(page.sourceText, "");
  assert.equal(page.ocrText, "Load capacity ≥ 300 kN");
  assert.equal(page.extractionMethod, "tesseract-ocr");
  assert.equal(page.ocrRegions[0].extractionMethod, "tesseract-ocr");
  assert.deepEqual(page.ocrRegions[0].bbox, { x: 20, y: 40, width: 100, height: 12 });
  assert.equal(reference.sourceText, "");
  assert.equal(reference.transcribedText, "Load capacity ≥ 300 kN");
  assert.equal(reference.extractionMethod, "tesseract-ocr");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.ocrConfidence, "medium");
  assert.equal(reference.startOffset, undefined);
});

test("records native and OCR evidence together on a mixed-content page", () => {
  const document = createSourceDocumentModel(new Uint8Array([10]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 4,
    width: 600,
    height: 800,
    sourceText: "Institute of Testing · Page 4",
    positionedItems: [{ start: 0, end: 29, text: "Institute of Testing · Page 4", box: { x: 20, y: 20, width: 140, height: 10 } }],
    hasRasterImageContent: true,
    ocrRecommended: true,
    ocrStatus: "text-found",
    ocrRegions: [{
      text: "Maximum pressure: 500 bar",
      bbox: { x: 30, y: 90, width: 200, height: 14 },
      confidence: 72,
      confidenceLevel: "medium",
    }],
  });

  assert.equal(page.extractionMethod, "pdfjs-native-text");
  assert.equal(page.hasRasterImageContent, true);
  assert.equal(page.ocrRecommended, true);
  assert.equal(page.ocrStatus, "text-found");
  assert.equal(page.sourceText, "Institute of Testing · Page 4");
  assert.equal(page.ocrText, "Maximum pressure: 500 bar");
  assert.equal(page.textBlocks[0].text, page.sourceText);
  assert.equal(page.ocrRegions[0].text, page.ocrText);
});

test("distinguishes skipped, empty, and failed OCR from pages where OCR was not recommended", () => {
  const document = createSourceDocumentModel(new Uint8Array([11]), 1);
  const makePage = (options) => buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 1,
    width: 100,
    height: 200,
    sourceText: "Header",
    positionedItems: [],
    hasRasterImageContent: true,
    ocrRecommended: true,
    ...options,
  });

  const skipped = makePage({ ocrStatus: "not-attempted", ocrSkipReason: "engine-unavailable" });
  const empty = makePage({ ocrStatus: "no-text-found" });
  const failed = makePage({ ocrStatus: "failed" });
  const ordinary = buildSourcePageModel({
    documentId: document.documentId,
    physicalPdfPageNumber: 2,
    width: 100,
    height: 200,
    sourceText: "Native page text",
    positionedItems: [],
  });

  assert.equal(skipped.ocrStatus, "not-attempted");
  assert.equal(skipped.ocrSkipReason, "engine-unavailable");
  assert.match(skipped.warnings.join(" "), /recommended but not attempted/);
  assert.equal(empty.ocrStatus, "no-text-found");
  assert.match(empty.warnings.join(" "), /completed but found no text/);
  assert.equal(failed.ocrStatus, "failed");
  assert.match(failed.warnings.join(" "), /did not complete/);
  assert.equal(ordinary.ocrStatus, "not-recommended");
  assert.deepEqual(ordinary.warnings, []);
});

test("does not report an unmatched model quote as source text", () => {
  const document = createSourceDocumentModel(new Uint8Array([5]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 1, width: 100, height: 200,
    sourceText: "A different selectable sentence", positionedItems: [],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "A model suggestion that is not on the page", bbox: null,
  });
  assert.equal(reference.sourceText, "");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.startOffset, undefined);
});

test("literal text with no bounding box retains offsets but never claims an exact visual location", () => {
  const document = createSourceDocumentModel(new Uint8Array([8]), 1);
  const page = buildSourcePageModel({
    documentId: document.documentId, physicalPdfPageNumber: 11,
    width: 300, height: 400, sourceText: "The instrument shall withstand 5 bar.", positionedItems: [],
  });
  const reference = buildRequirementSourceReference({
    document, page, quote: "The instrument shall withstand 5 bar.", bbox: null,
  });
  assert.equal(reference.sourceText, "The instrument shall withstand 5 bar.");
  assert.equal(reference.locationPrecision, "approximate");
  assert.equal(reference.bbox, null);
  assert.equal(reference.physicalPdfPageNumber, 11);
  assert.equal(reference.startOffset, 0);
  assert.equal(reference.endOffset, "The instrument shall withstand 5 bar.".length);
});
