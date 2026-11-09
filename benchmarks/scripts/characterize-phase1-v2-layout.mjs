#!/usr/bin/env node
import { execFile as execFileCallback } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { createCanvas, DOMMatrix, ImageData, loadImage, Path2D } from "../../apps/web/node_modules/@napi-rs/canvas/index.js";
import {
  buildSourcePageModel,
  createSourceDocumentModel,
  validateSourceDocumentInventory,
} from "../../apps/web/app/source-document.ts";
import {
  createPopplerPageRenderer,
  isPopplerAvailable,
  isTesseractAvailable,
  offsetOcrPageText,
  recognizePageImage,
  resolveTesseractBinary,
  resolveTesseractLanguage,
} from "../../apps/web/app/local-ocr.ts";
import { selectImageRegionsForOcr } from "../../apps/web/app/ocr-routing.ts";
import { inspectDocument } from "./inventory-phase1-v2-pages.mjs";
import { validateManifest } from "./verify-phase1-v2-corpus.mjs";

Object.assign(globalThis, { DOMMatrix, ImageData, Path2D });
const execFile = promisify(execFileCallback);
const MAX_OCR_PAGES_PER_DOCUMENT = 120;
const MAX_TOTAL_OCR_MS_PER_DOCUMENT = 210_000;
const MAX_OCR_REGIONS_PER_PAGE = 6;
const OCR_RENDER_MAX_DIMENSION = 1700;

export function summarizeLayoutCharacterization(documents) {
  const pages = documents.flatMap((document) => document.pages);
  const imageRegions = pages.flatMap((page) => page.imageRegions);
  const countBy = (items, getKey) => items.reduce((counts, item) => {
    const key = getKey(item);
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
  return {
    documents: documents.length,
    physicalPages: pages.length,
    parserInventoryIssues: documents.reduce((sum, document) => sum + document.sourceInventoryIssueCount, 0),
    parserInventoryIssueCodes: documents.reduce((counts, document) => {
      for (const [code, value] of Object.entries(document.sourceInventoryIssueCodes)) counts[code] = (counts[code] ?? 0) + value;
      return counts;
    }, {}),
    pagesByOcrStatus: countBy(pages, (page) => page.ocrStatus),
    pagesByOcrInputMode: countBy(pages, (page) => page.ocrInputMode),
    imageRegionsByDisposition: countBy(imageRegions, (region) => region.disposition),
    targetedImageRegions: imageRegions.filter((region) => region.targeted).length,
    ocrLines: pages.reduce((sum, page) => sum + page.ocrLineCount, 0),
    ocrWords: pages.reduce((sum, page) => sum + page.ocrWordCount, 0),
    pagesWithVectorTableCandidates: pages.filter((page) => page.vectorTableGeometryCandidate).length,
    vectorRowCandidates: pages.reduce((sum, page) => sum + page.vectorRowCandidateCount, 0),
    vectorCellTextCandidates: pages.reduce((sum, page) => sum + page.vectorCellTextCandidateCount, 0),
    ocrExecuted: pages.some((page) => page.ocrAttempted),
    modelCalls: 0,
    sourceTextStored: false,
    ocrTextStored: false,
    boundingBoxesStored: false,
  };
}

export function resolveImageRegionDisposition(input) {
  if (!input.targeted) return { disposition: "not-targeted" };
  if (input.pageOcrStatus === "failed") return { disposition: "failed" };
  if (input.pageOcrStatus !== "text-found" && input.pageOcrStatus !== "no-text-found") {
    return { disposition: "not-attempted", skipReason: input.skipReason ?? "time-budget" };
  }
  if (!input.attempted) return { disposition: "not-attempted", skipReason: input.skipReason ?? "region-limit" };
  return { disposition: input.textFound ? "text-found" : "no-text-found" };
}

async function inspectWithLocalOcr(document, examplesDirectory) {
  const path = resolve(examplesDirectory, document.fileName);
  const bytes = await readFile(path);
  const sourceDocument = createSourceDocumentModel(bytes, document.physicalPages);
  let tesseractAvailable;
  let popplerAvailable;
  let renderer;
  let attemptedPages = 0;
  const ocrStartedAt = Date.now();
  const inspectPage = async (input) => {
    const nativeBoxes = input.positionedItems.map((item) => item.box);
    const targets = input.rawText.trim()
      ? selectImageRegionsForOcr(input.imageRegions, nativeBoxes)
      : [];
    let ocrStatus = input.ocrRecommended ? "not-attempted" : "not-recommended";
    let ocrSkipReason;
    let ocrAttempted = false;
    let ocrInputMode = "none";
    let ocrLines = [];

    if (input.ocrRecommended) {
      if (attemptedPages >= MAX_OCR_PAGES_PER_DOCUMENT) ocrSkipReason = "page-limit";
      else if (Date.now() - ocrStartedAt >= MAX_TOTAL_OCR_MS_PER_DOCUMENT) ocrSkipReason = "time-budget";
      else {
        if (tesseractAvailable === undefined) tesseractAvailable = await isTesseractAvailable();
        if (!tesseractAvailable) ocrSkipReason = "engine-unavailable";
        else {
          attemptedPages += 1;
          ocrAttempted = true;
          ocrStatus = "failed";
          try {
            if (popplerAvailable === undefined) popplerAvailable = await isPopplerAvailable();
            let image;
            let imageSize;
            if (popplerAvailable) {
              if (!renderer) renderer = createPopplerPageRenderer(bytes);
              image = await renderer.renderPage(input.pageNumber, OCR_RENDER_MAX_DIMENSION);
              const rendered = await loadImage(Buffer.from(image));
              imageSize = { width: rendered.width, height: rendered.height };
            } else {
              const scale = Math.min(2, OCR_RENDER_MAX_DIMENSION / Math.max(input.viewport.width, input.viewport.height));
              const ocrViewport = input.page.getViewport({ scale });
              const canvas = createCanvas(Math.ceil(ocrViewport.width), Math.ceil(ocrViewport.height));
              await input.page.render({ canvasContext: canvas.getContext("2d"), viewport: ocrViewport }).promise;
              image = canvas.toBuffer("image/png");
              imageSize = { width: canvas.width, height: canvas.height };
            }

            if (targets.length) {
              ocrInputMode = "image-regions";
              const rendered = await loadImage(Buffer.from(image));
              const scaleX = imageSize.width / input.viewport.width;
              const scaleY = imageSize.height / input.viewport.height;
              const attemptedRegionIndices = new Set();
              let attemptedCount = 0;
              for (const target of targets.slice(0, MAX_OCR_REGIONS_PER_PAGE)) {
                if (Date.now() - ocrStartedAt >= MAX_TOTAL_OCR_MS_PER_DOCUMENT) {
                  ocrSkipReason = "time-budget";
                  break;
                }
                const left = Math.max(0, Math.floor(target.bbox.x * scaleX));
                const top = Math.max(0, Math.floor(target.bbox.y * scaleY));
                const right = Math.min(imageSize.width, Math.ceil((target.bbox.x + target.bbox.width) * scaleX));
                const bottom = Math.min(imageSize.height, Math.ceil((target.bbox.y + target.bbox.height) * scaleY));
                if (right <= left || bottom <= top) continue;
                const crop = createCanvas(right - left, bottom - top);
                crop.getContext("2d").drawImage(rendered, left, top, right - left, bottom - top, 0, 0, right - left, bottom - top);
                attemptedRegionIndices.add(target.index);
                const result = await recognizePageImage({
                  image: crop.toBuffer("image/png"),
                  imageSize: { width: right - left, height: bottom - top },
                  pageSize: { width: target.bbox.width, height: target.bbox.height },
                });
                ocrLines.push(...offsetOcrPageText(result, { x: target.bbox.x, y: target.bbox.y }, target.index).lines);
                attemptedCount += 1;
              }
              if (targets.length > attemptedCount && !ocrSkipReason) ocrSkipReason = "region-limit";
              input.attemptedRegionIndices = attemptedRegionIndices;
            } else {
              ocrInputMode = "full-page";
              const result = await recognizePageImage({
                image,
                imageSize,
                pageSize: { width: input.viewport.width, height: input.viewport.height },
              });
              ocrLines = result.lines;
            }
            ocrStatus = ocrLines.length > 0 ? "text-found" : "no-text-found";
          } catch {
            ocrStatus = "failed";
            ocrLines = [];
          }
        }
      }
    }

    const attemptedRegionIndices = input.attemptedRegionIndices ?? new Set();
    const imageRegionRecords = input.imageRegions.map((region, index) => {
      const targeted = targets.some((target) => target.index === index);
      const status = resolveImageRegionDisposition({
        targeted,
        pageOcrStatus: ocrStatus,
        attempted: attemptedRegionIndices.has(index),
        skipReason: ocrSkipReason,
        textFound: ocrLines.some((line) => line.imageRegionIndex === index),
      });
      return {
        id: `${sourceDocument.documentId}:page:${input.pageNumber}:image:${index + 1}`,
        index,
        operator: region.operator,
        areaRatio: Math.round(region.areaRatio * 1_000_000) / 1_000_000,
        targeted,
        disposition: status.disposition,
        ...(status.skipReason ? { skipReason: status.skipReason } : {}),
      };
    });
    const sourcePage = buildSourcePageModel({
      documentId: sourceDocument.documentId,
      physicalPdfPageNumber: input.pageNumber,
      width: input.viewport.width,
      height: input.viewport.height,
      sourceText: input.rawText,
      positionedItems: input.positionedItems,
      hasRasterImageContent: input.hasRasterImageContent,
      ocrRecommended: input.ocrRecommended,
      ocrStatus,
      ocrSkipReason,
      imageRegions: input.imageRegions.map((region, index) => ({
        ...region,
        ocrDisposition: imageRegionRecords[index].disposition,
        ...(imageRegionRecords[index].skipReason ? { ocrSkipReason: imageRegionRecords[index].skipReason } : {}),
      })),
      ocrRegions: ocrLines,
      vectorRows: input.vectorRows,
    });
    sourceDocument.pages.push(sourcePage);
    const confidenceCounts = ocrLines.reduce((counts, line) => {
      counts[line.confidenceLevel] += 1;
      return counts;
    }, { high: 0, medium: 0, low: 0 });
    if (ocrAttempted && attemptedPages % 10 === 0) {
      process.stderr.write(`${document.id}: OCR attempted on ${attemptedPages} recommended pages so far.\n`);
    }

    return {
      ocrStatus,
      ...(ocrSkipReason ? { ocrSkipReason } : {}),
      ocrExecuted: ocrAttempted,
      ocrAttempted,
      ocrInputMode,
      ocrLineCount: ocrLines.length,
      ocrWordCount: ocrLines.reduce((sum, line) => sum + line.words.length, 0),
      ocrConfidenceLineCounts: confidenceCounts,
      imageRegions: imageRegionRecords,
    };
  };

  try {
    const result = await inspectDocument(document, examplesDirectory, inspectPage);
    const allIssues = validateSourceDocumentInventory(sourceDocument);
    const sourceInventoryIssueCodes = allIssues.reduce((counts, issue) => {
      counts[issue.code] = (counts[issue.code] ?? 0) + 1;
      return counts;
    }, {});
    return {
      ...result,
      pages: result.pages.map((page) => ({
        ...page,
        sourceInventoryIssueCodes: allIssues.filter((issue) => issue.page === page.physicalPage).map((issue) => issue.code),
      })),
      sourceInventoryIssueCount: allIssues.length,
      sourceInventoryIssueCodes,
      ocrAttemptedPages: attemptedPages,
    };
  } finally {
    await renderer?.close();
  }
}

function parseArguments(args) {
  const options = { examples: "examples", manifest: "benchmarks/phase-1-v2-corpus.json", output: "" };
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === "--examples" && args[index + 1]) options.examples = args[++index];
    else if (args[index] === "--manifest" && args[index + 1]) options.manifest = args[++index];
    else if (args[index] === "--output" && args[index + 1]) options.output = args[++index];
    else throw new Error("Usage: node benchmarks/scripts/characterize-phase1-v2-layout.mjs [--examples directory] [--manifest file.json] [--output file.json]");
  }
  return options;
}

export async function main(argv = process.argv.slice(2)) {
  const options = parseArguments(argv);
  const examplesDirectory = resolve(options.examples);
  const manifest = JSON.parse(await readFile(resolve(options.manifest), "utf8"));
  const fileNames = manifest.documents.map((document) => document.fileName);
  validateManifest(manifest, fileNames);
  const tesseractVersion = (await execFile(resolveTesseractBinary(), ["--version"], { maxBuffer: 64 * 1024 })).stdout.split(/\r?\n/u)[0];
  const documents = [];
  for (const document of manifest.documents) {
    process.stderr.write(`${document.id}: starting ${document.physicalPages}-page local layout/OCR characterization.\n`);
    const result = await inspectWithLocalOcr(document, examplesDirectory);
    documents.push(result);
    process.stderr.write(`${document.id}: finished; OCR attempted on ${result.ocrAttemptedPages} pages, inventory issues ${result.sourceInventoryIssueCount}.\n`);
  }
  const result = {
    schemaVersion: 1,
    corpusId: manifest.corpusId,
    parser: "PDF.js and current TCE source-inventory helpers",
    ocrEngine: tesseractVersion,
    ocrRenderer: "Poppler pdftoppm when available, otherwise PDF.js canvas",
    ocrLanguage: resolveTesseractLanguage(),
    perDocumentLimits: {
      maxRecommendedPagesAttempted: MAX_OCR_PAGES_PER_DOCUMENT,
      maxOcrWallClockMs: MAX_TOTAL_OCR_MS_PER_DOCUMENT,
      maxImageRegionsPerPage: MAX_OCR_REGIONS_PER_PAGE,
      maxRenderDimension: OCR_RENDER_MAX_DIMENSION,
    },
    sourceTextStored: false,
    ocrTextStored: false,
    boundingBoxesStored: false,
    modelCalls: 0,
    documents,
    summary: summarizeLayoutCharacterization(documents),
    limitations: [
      "OCR line/word counts and confidence are processing diagnostics, not OCR accuracy or semantic completeness measures.",
      "Scan-only pages use full-page OCR; their image operators are not individually linked to OCR text and remain not-targeted at image-region level.",
      "Vector row/cell counts come from the current bordered-geometry helper and are candidates; they do not confirm correct table reconstruction.",
      "This artifact does not confirm cross-page table continuations, annexure links, obligation coverage, or semantic relevance.",
      "OCR results are kept in memory only; the artifact stores no native text, OCR transcript, source bounds, or OCR bounding boxes.",
    ],
  };
  const json = `${JSON.stringify(result, null, 2)}\n`;
  if (options.output) await writeFile(resolve(options.output), json, { encoding: "utf8", flag: "w" });
  process.stdout.write(options.output ? `${JSON.stringify({ passed: true, output: resolve(options.output), summary: result.summary })}\n` : json);
  return result.summary;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Layout characterization failed."}\n`);
    process.exitCode = 1;
  });
}
