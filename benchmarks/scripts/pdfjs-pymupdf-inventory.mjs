#!/usr/bin/env node
/**
 * Compare page-level inventory signals from the production PDF.js parser and
 * the optional PyMuPDF shadow artifact. Emits counts only, never source text.
 * Run from the repository root with:
 *   node --experimental-strip-types benchmarks/scripts/pdfjs-pymupdf-inventory.mjs
 */
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { getDocument, OPS } from '../../apps/web/node_modules/pdfjs-dist/legacy/build/pdf.mjs';
import { DOMMatrix, ImageData, Path2D } from '../../apps/web/node_modules/@napi-rs/canvas/index.js';
import { collectPdfImageRegions } from '../../apps/web/app/pdf-image-regions.ts';

Object.assign(globalThis, { DOMMatrix, ImageData, Path2D });
let pdfjsWarningCount = 0;
const originalWarn = console.warn;
console.warn = (...args) => {
  pdfjsWarningCount += 1;
  originalWarn(...args);
};
const originalLog = console.log;
console.log = (...args) => {
  if (typeof args[0] === 'string' && args[0].startsWith('Warning: TT:')) {
    pdfjsWarningCount += 1;
    return;
  }
  originalLog(...args);
};

const manifestUrl = new URL('../representative-tenders/manifest.json', import.meta.url);
const pymupdfUrl = new URL('../representative-tenders/page-inventory-shadow-2026-11-07.json', import.meta.url);
const pdfjsPackageUrl = new URL('../../apps/web/node_modules/pdfjs-dist/package.json', import.meta.url);
const manifest = JSON.parse(await readFile(manifestUrl, 'utf8'));
const pymupdf = JSON.parse(await readFile(pymupdfUrl, 'utf8'));
const pymupdfById = new Map(pymupdf.documents.map((document) => [document.id, document]));
const runtimeCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: new URL('../../', import.meta.url), encoding: 'utf8' }).trim();

async function inspectPdfJs(document) {
  const bytes = await readFile(document.pathHint);
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  if (sha256 !== document.sha256) throw new Error(`Source fingerprint mismatch for ${document.id}`);
  const pdf = await getDocument({ data: new Uint8Array(bytes), useSystemFonts: true, disableFontFace: true }).promise;
  try {
    const pages = [];
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 1 });
      const content = await page.getTextContent();
      const textItems = content.items.filter((item) => typeof item.str === 'string');
      let nativeText = '';
      for (const item of textItems) {
        nativeText += item.str;
        if (item.hasEOL) nativeText += '\n';
      }
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
      const pageArea = viewport.width * viewport.height;
      const imageArea = imageRegions.reduce((sum, region) => sum + region.bbox.width * region.bbox.height, 0);
      pages.push({
        page: pageNumber,
        width: round(viewport.width),
        height: round(viewport.height),
        nativeTextChars: nativeText.trim().length,
        nativeWords: textItems.reduce((sum, item) => sum + (item.str.trim() ? item.str.trim().split(/\s+/).length : 0), 0),
        nativeTextItems: textItems.length,
        imageRegions: imageRegions.length,
        imageAreaRatio: pageArea ? round(Math.min(1, imageArea / pageArea), 6) : 0,
        pathOperators: operators.fnArray.filter((code) => code === OPS.constructPath).length,
      });
      page.cleanup();
    }
    return { sha256, pageCount: pdf.numPages, pages };
  } finally {
    await pdf.destroy();
  }
}

function round(value) { return Math.round(value * 100) / 100; }
function delta(left, right) { return round(left - right); }

const documents = [];
for (const expected of manifest.documents) {
  const shadow = pymupdfById.get(expected.id);
  if (!shadow || shadow.sha256 !== expected.sha256) throw new Error(`Missing or mismatched PyMuPDF shadow record for ${expected.id}`);
  const parsed = await inspectPdfJs(expected);
  if (parsed.pageCount !== expected.pages || shadow.pages !== expected.pages) throw new Error(`Page-count mismatch for ${expected.id}`);
  const shadowPages = new Map(shadow.pageInventory.map((page) => [page.page, page]));
  const comparison = parsed.pages.map((pdfjs) => {
    const pymupdfPage = shadowPages.get(pdfjs.page);
    if (!pymupdfPage) throw new Error(`PyMuPDF shadow page missing: ${expected.id}:${pdfjs.page}`);
    return {
      page: pdfjs.page,
      pdfjs: {
        width: pdfjs.width, height: pdfjs.height,
        nativeTextChars: pdfjs.nativeTextChars, nativeWords: pdfjs.nativeWords,
        nativeTextItems: pdfjs.nativeTextItems, imageRegions: pdfjs.imageRegions,
        imageAreaRatio: pdfjs.imageAreaRatio, pathOperators: pdfjs.pathOperators,
      },
      pymupdf: {
        width: pymupdfPage.width, height: pymupdfPage.height,
        nativeTextChars: pymupdfPage.nativeTextChars, nativeWords: pymupdfPage.nativeWords,
        nativeTextBlocks: pymupdfPage.nativeTextBlocks, imageRegions: pymupdfPage.imageRegions,
        imageAreaRatio: pymupdfPage.imageAreaRatio, vectorDrawingCount: pymupdfPage.vectorDrawingCount,
      },
      delta: {
        width: round(pdfjs.width - pymupdfPage.width),
        height: round(pdfjs.height - pymupdfPage.height),
        imageRegions: pdfjs.imageRegions - pymupdfPage.imageRegions,
        imageAreaRatio: delta(pdfjs.imageAreaRatio, pymupdfPage.imageAreaRatio),
        pathOperatorsVsVectorDrawings: pdfjs.pathOperators - pymupdfPage.vectorDrawingCount,
      },
    };
  });
  documents.push({
    id: expected.id,
    filename: expected.filename,
    sha256: parsed.sha256,
    pages: parsed.pageCount,
    coordinateSystems: { pdfjs: 'pdfjs-viewport-scale-1', pymupdf: 'pymupdf-page-points' },
    pageComparison: comparison,
  });
}

const result = {
  schemaVersion: 1,
  runDate: new Date().toISOString().slice(0, 10),
  runtimeCommit,
  pdfjsVersion: JSON.parse(await readFile(pdfjsPackageUrl, 'utf8')).version,
  pymupdfVersion: pymupdf.pymupdfVersion,
  sourceTextIncluded: false,
  elementBoundsIncluded: false,
  pdfjsWarningCount,
  documents,
  comparisonSummary: (() => {
    const pages = documents.flatMap((document) => document.pageComparison);
    return {
      pagesCompared: pages.length,
      pageDimensionMismatches: pages.filter((page) => page.delta.width !== 0 || page.delta.height !== 0).length,
      imageRegionCountMismatches: pages.filter((page) => page.delta.imageRegions !== 0).length,
      imageAreaRatioMismatches: pages.filter((page) => page.delta.imageAreaRatio !== 0).length,
      vectorOperatorCountDiffersFromDrawingObjectCount: pages.filter((page) => page.delta.pathOperatorsVsVectorDrawings !== 0).length,
      textMetricsAreSideBySideOnly: true,
    };
  })(),
  limitations: [
    'Counts and coordinate systems are parser diagnostics, not table or requirement precision/recall.',
    'PDF.js nativeTextItems are positioned text objects, not semantic text blocks; PyMuPDF nativeTextBlocks are parser text blocks.',
    'Image draw counts can differ because parser operators and image placements are not one-to-one.',
    'Image-area ratios sum approximate draw bounds and may double-count overlaps.',
    'pathOperators and vectorDrawingCount are different parser primitives, not equivalent table-grid counts.',
  ],
};
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
