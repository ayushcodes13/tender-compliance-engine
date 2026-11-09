#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { getDocument, OPS } from "../../apps/web/node_modules/pdfjs-dist/legacy/build/pdf.mjs";
import { DOMMatrix, ImageData, Path2D } from "../../apps/web/node_modules/@napi-rs/canvas/index.js";
import { collectPdfImageRegions } from "../../apps/web/app/pdf-image-regions.ts";
import { extractVectorTableRows } from "../../apps/web/app/vector-table.ts";
import { extractPdfPathRectangles, hasTableGridGeometry } from "../../apps/web/app/pdf-path-rectangles.ts";
import { findAnnexureHeading, findTechnicalSectionHeading } from "../../apps/web/app/annexure-routing.ts";
import { hasRasterImageOperators, selectImageRegionsForOcr, shouldRunPageOcr } from "../../apps/web/app/ocr-routing.ts";
import { PDF_FONT_OPTIONS } from "../../apps/web/app/pdf-runtime.ts";
import { validateManifest } from "./verify-phase1-v2-corpus.mjs";

Object.assign(globalThis, { DOMMatrix, ImageData, Path2D });
let pdfjsWarningCount = 0;
const originalWarn = console.warn;
console.warn = (...args) => {
  pdfjsWarningCount += 1;
  originalWarn(...args);
};
const originalLog = console.log;
console.log = (...args) => {
  if (typeof args[0] === "string" && args[0].startsWith("Warning: TT:")) {
    pdfjsWarningCount += 1;
    return;
  }
  originalLog(...args);
};

const IMAGE_OPERATOR_CODES = [
  OPS.paintImageXObject,
  OPS.paintInlineImageXObject,
  OPS.paintImageMaskXObject,
  OPS.paintImageMaskXObjectGroup,
  OPS.paintInlineImageXObjectGroup,
  OPS.paintImageXObjectRepeat,
  OPS.paintImageMaskXObjectRepeat,
];

function round(value, digits = 3) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function pageItemBox(item, viewport) {
  const [a, b, c, d, e, f] = item.transform;
  const baseLength = Math.hypot(a, b) || 1;
  const verticalLength = Math.hypot(c, d) || 1;
  const ux = (a / baseLength) * item.width;
  const uy = (b / baseLength) * item.width;
  const vx = (c / verticalLength) * item.height;
  const vy = (d / verticalLength) * item.height;
  const points = [
    viewport.convertToViewportPoint(e, f),
    viewport.convertToViewportPoint(e + ux, f + uy),
    viewport.convertToViewportPoint(e + vx, f + vy),
    viewport.convertToViewportPoint(e + ux + vx, f + uy + vy),
  ];
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  const width = Math.max(...xs) - x;
  const height = Math.max(...ys) - y;
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
  return { x, y, width, height };
}

function deduplicateRectangles(rectangles, rectangle) {
  if (!rectangles.some((seen) => Math.abs(seen.x - rectangle.x) < 0.2
    && Math.abs(seen.y - rectangle.y) < 0.2
    && Math.abs(seen.width - rectangle.width) < 0.2
    && Math.abs(seen.height - rectangle.height) < 0.2)) rectangles.push(rectangle);
}

function tableRectangles(operatorList, viewport) {
  const rectangles = [];
  const pathRectangles = [];
  for (let index = 0; index < operatorList.fnArray.length; index += 1) {
    if (operatorList.fnArray[index] !== OPS.constructPath) continue;
    const [commands, coordinates] = operatorList.argsArray[index];
    const outlines = extractPdfPathRectangles(commands, coordinates, {
      rectangle: OPS.rectangle,
      moveTo: OPS.moveTo,
      lineTo: OPS.lineTo,
      closePath: OPS.closePath,
    }, 0.1, 0.1);
    for (const rectangle of outlines) {
      deduplicateRectangles(pathRectangles, rectangle);
      const horizontalRule = rectangle.width > viewport.width * 0.05 && rectangle.height <= 2.5;
      const verticalRule = rectangle.width <= 2.5 && rectangle.height > viewport.height * 0.05;
      if (!horizontalRule && !verticalRule && (rectangle.width <= 30 || rectangle.height <= 5)) continue;
      deduplicateRectangles(rectangles, rectangle);
    }
  }
  return { rectangles, pathRectangles };
}

export function summarizePageInventory(documents) {
  const pages = documents.flatMap((document) => document.pages);
  return {
    documents: documents.length,
    pages: pages.length,
    pagesWithNativeText: pages.filter((page) => page.nativeTextChars > 0).length,
    pagesWithRasterImageSignals: pages.filter((page) => page.imageRegionCount > 0).length,
    pagesWithBothTextAndRasterSignals: pages.filter((page) => page.nativeTextChars > 0 && page.imageRegionCount > 0).length,
    pagesWithVectorTableGeometryCandidates: pages.filter((page) => page.vectorTableGeometryCandidate).length,
    pagesWithVectorRowCandidates: pages.filter((page) => page.vectorRowCandidateCount > 0).length,
    vectorRowCandidates: pages.reduce((sum, page) => sum + page.vectorRowCandidateCount, 0),
    pagesWithNativeAnnexureHeadingCandidates: pages.filter((page) => page.nativeAnnexureHeadingCandidate).length,
    pagesWithNativeTechnicalHeadingCandidates: pages.filter((page) => page.nativeTechnicalHeadingCandidate).length,
    pagesRecommendedForOcrByCurrentRouter: pages.filter((page) => page.currentRouterWouldRecommendOcr).length,
    selectedImageRegionsByCurrentRouter: pages.reduce((sum, page) => sum + page.currentRouterOcrTargetRegionCount, 0),
    ocrExecuted: false,
    modelCalls: 0,
    sourceTextStored: false,
  };
}

export async function inspectDocument(document, examplesDirectory, inspectPage = null) {
  const path = join(examplesDirectory, document.fileName);
  const bytes = await readFile(path);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  if (sha256 !== document.sha256) throw new Error(`${document.fileName}: SHA-256 does not match the corpus manifest.`);

  const pdf = await getDocument({ data: new Uint8Array(bytes), isEvalSupported: false, ...PDF_FONT_OPTIONS }).promise;
  try {
    if (pdf.numPages !== document.physicalPages) throw new Error(`${document.fileName}: PDF.js page count does not match the corpus manifest.`);
    const pages = [];
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 1 });
      const content = await page.getTextContent({ disableNormalization: true });
      const sourceItems = [];
      const positionedItems = [];
      let rawText = "";
      for (const item of content.items) {
        if (!("str" in item) || typeof item.str !== "string" || !item.str) continue;
        if (rawText && !rawText.endsWith("\n")) rawText += " ";
        const start = rawText.length;
        rawText += item.str;
        const end = rawText.length;
        if (item.hasEOL) rawText += "\n";
        const box = pageItemBox(item, viewport);
        const [, , , , x, y] = item.transform;
        sourceItems.push({ str: item.str, x, y, box });
        if (box) positionedItems.push({ start, end, text: item.str, box });
      }
      const normalizedNativeText = rawText.replace(/\s+/gu, " ").trim();
      const nativeTextChars = normalizedNativeText.length;
      const nativeWordCount = normalizedNativeText ? normalizedNativeText.split(/\s+/u).length : 0;

      const operators = await page.getOperatorList();
      const imageRegions = collectPdfImageRegions({
        fnArray: operators.fnArray,
        argsArray: operators.argsArray,
        codes: {
          save: OPS.save,
          restore: OPS.restore,
          transform: OPS.transform,
          paintFormXObjectBegin: OPS.paintFormXObjectBegin,
          paintFormXObjectEnd: OPS.paintFormXObjectEnd,
          image: [OPS.paintImageXObject, OPS.paintInlineImageXObject, OPS.paintImageMaskXObject],
          imageGroup: [OPS.paintImageMaskXObjectGroup, OPS.paintInlineImageXObjectGroup],
          imageRepeat: [OPS.paintImageXObjectRepeat],
          imageMaskRepeat: [OPS.paintImageMaskXObjectRepeat],
        },
        viewportTransform: viewport.transform,
        pageSize: { width: viewport.width, height: viewport.height },
      });
      const hasRasterImageContent = hasRasterImageOperators(operators.fnArray, IMAGE_OPERATOR_CODES);
      const pageArea = viewport.width * viewport.height;
      const nativeTextAreaRatio = pageArea > 0
        ? sourceItems.reduce((sum, item) => sum + (item.box?.width ?? 0) * (item.box?.height ?? 0), 0) / pageArea
        : 0;
      const currentRouterOcrTargetRegionCount = rawText.trim()
        ? selectImageRegionsForOcr(imageRegions, sourceItems.flatMap((item) => item.box ? [item.box] : [])).length
        : 0;
      const currentRouterWouldRecommendOcr = shouldRunPageOcr({
        selectableText: rawText,
        textAreaRatio: nativeTextAreaRatio,
        hasRasterImageContent,
        imageRegions,
        nativeTextBoxes: sourceItems.flatMap((item) => item.box ? [item.box] : []),
      });
      const { rectangles, pathRectangles } = tableRectangles(operators, viewport);
      const vectorTableGeometryCandidate = rectangles.length >= 8
        || hasTableGridGeometry(pathRectangles, viewport.width, viewport.height);
      const vectorRows = vectorTableGeometryCandidate
        ? extractVectorTableRows(sourceItems, rectangles, viewport.width, viewport.height)
        : [];
      const imageAreaRatio = pageArea > 0
        ? Math.min(1, imageRegions.reduce((sum, region) => sum + region.bbox.width * region.bbox.height, 0) / pageArea)
        : 0;
      const pageRecord = {
        physicalPage: pageNumber,
        width: round(viewport.width, 2),
        height: round(viewport.height, 2),
        nativeTextChars,
        nativeWordCount,
        nativeTextItemCount: sourceItems.length,
        imageRegionCount: imageRegions.length,
        imageAreaRatioSumApprox: round(imageAreaRatio, 5),
        hasRasterImageOperators: hasRasterImageContent,
        hasNativeTextAndRasterImageSignals: nativeTextChars > 0 && hasRasterImageContent,
        nativeAnnexureHeadingCandidate: Boolean(findAnnexureHeading(positionedItems, viewport.height)),
        nativeTechnicalHeadingCandidate: Boolean(findTechnicalSectionHeading(positionedItems, viewport.height)),
        vectorPathRectangleCount: pathRectangles.length,
        vectorTableGeometryCandidate,
        vectorRowCandidateCount: vectorRows.length,
        vectorCellTextCandidateCount: vectorRows.reduce((sum, row) => sum + row.cells.filter(Boolean).length, 0),
        currentRouterWouldRecommendOcr,
        currentRouterOcrTargetRegionCount,
        ocrExecuted: false,
      };
      const extraPageData = inspectPage
        ? await inspectPage({
          page,
          pageNumber,
          pageCount: pdf.numPages,
          viewport,
          rawText,
          sourceItems,
          positionedItems,
          imageRegions,
          hasRasterImageContent,
          ocrRecommended: currentRouterWouldRecommendOcr,
          vectorRows,
        })
        : null;
      if (extraPageData && typeof extraPageData === "object") Object.assign(pageRecord, extraPageData);
      pages.push(pageRecord);
      page.cleanup();
    }
    return { id: document.id, fileName: document.fileName, familyGroupId: document.familyGroupId, sha256, physicalPages: pages.length, pages };
  } finally {
    await pdf.destroy();
  }
}

function parseArguments(args) {
  const options = { examples: "examples", manifest: "benchmarks/phase-1-v2-corpus.json", output: "" };
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === "--examples" && args[index + 1]) options.examples = args[++index];
    else if (args[index] === "--manifest" && args[index + 1]) options.manifest = args[++index];
    else if (args[index] === "--output" && args[index + 1]) options.output = args[++index];
    else throw new Error("Usage: node benchmarks/scripts/inventory-phase1-v2-pages.mjs [--examples directory] [--manifest file.json] [--output file.json]");
  }
  return options;
}

export async function main(argv = process.argv.slice(2)) {
  const options = parseArguments(argv);
  const examplesDirectory = resolve(options.examples);
  const manifest = JSON.parse(await readFile(resolve(options.manifest), "utf8"));
  const fileNames = (await readdir(examplesDirectory)).filter((name) => name.toLowerCase().endsWith(".pdf")).sort();
  validateManifest(manifest, fileNames);
  const documents = [];
  for (const document of manifest.documents) documents.push(await inspectDocument(document, examplesDirectory));
  const result = {
    schemaVersion: 1,
    corpusId: manifest.corpusId,
    parser: "PDF.js with current TCE image-region, vector-table, annexure-heading, and OCR-routing helpers",
    nativeTextStored: false,
    boundingBoxesStored: false,
    ocrExecuted: false,
    modelCalls: 0,
    pdfjsWarningCount,
    documents,
    summary: summarizePageInventory(documents),
    limitations: [
      "Image/text coexistence is a parser signal, not proof that a page is hybrid or that text covers the raster image.",
      "Image-region bounds and summed image area are approximate and may overlap or count decorative graphics.",
      "Vector row/cell counts are candidates from the current bordered-geometry parser, not table recall; borderless structures may be absent.",
      "Heading flags are native-text candidates only; they do not establish annexure linkage or cross-page continuation.",
      "OCR recommendations are recomputed from current routing helpers; no OCR was run and these are not actual OCR dispositions.",
      "This inventory does not classify technical obligations or replace source-region human annotation.",
    ],
  };
  const json = `${JSON.stringify(result, null, 2)}\n`;
  if (options.output) await writeFile(resolve(options.output), json, { encoding: "utf8", flag: "w" });
  else process.stdout.write(json);
  return result.summary;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Page inventory failed."}\n`);
    process.exitCode = 1;
  });
}
