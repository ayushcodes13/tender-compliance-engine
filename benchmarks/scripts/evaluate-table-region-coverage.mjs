#!/usr/bin/env node
/**
 * Compare parser table-candidate bounds with source-bound annotations.
 * This measures geometric coverage only; it is not table accuracy or recall.
 * Usage:
 * node --experimental-strip-types benchmarks/scripts/evaluate-table-region-coverage.mjs \
 *   --source /absolute/path/to/iitg-utm.pdf \
 *   --annotation benchmarks/representative-tenders/heldout-golden-v0.3.json \
 *   --annotation benchmarks/representative-tenders/heldout-golden-v0.4.json \
 *   --annotation benchmarks/representative-tenders/heldout-golden-v0.5.json
 */
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

function parseArgs(argv) {
  let source;
  const annotations = [];
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--source') source = argv[++index];
    else if (argv[index] === '--annotation') annotations.push(argv[++index]);
    else throw new Error(`Unknown or incomplete argument: ${argv[index]}`);
  }
  if (!source || !annotations.length) throw new Error('Both --source and at least one --annotation are required.');
  return { source, annotations };
}

function intersectionArea(a, b) {
  return Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x))
    * Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
}

function summarize(values) {
  const sorted = [...values].sort((left, right) => left - right);
  return {
    annotationsWithBounds: sorted.length,
    sourceCoverageAtLeast95Percent: sorted.filter((value) => value >= 0.95).length,
    sourceCoverageAtLeast50Percent: sorted.filter((value) => value >= 0.5).length,
    medianBestSourceCoverage: sorted.length ? Math.round(sorted[Math.floor(sorted.length / 2)] * 1000) / 1000 : null,
  };
}

const { source, annotations: annotationPaths } = parseArgs(process.argv.slice(2));
const sourceBytes = await readFile(source);
const sourceSha256 = createHash('sha256').update(sourceBytes).digest('hex');
const annotationDocuments = await Promise.all(annotationPaths.map(async (path) => ({
  path,
  value: JSON.parse(await readFile(path, 'utf8')),
})));
for (const { path, value } of annotationDocuments) {
  if (value.sourceSha256 !== sourceSha256) throw new Error(`Source fingerprint does not match annotation ${path}`);
}

const latestById = new Map();
for (const { path, value } of annotationDocuments) {
  for (const item of value.cases ?? []) {
    if (item?.id && Number.isInteger(item.page) && item.bounds) latestById.set(item.id, { ...item, annotationArtifact: path });
  }
}
const cases = [...latestById.values()].sort((left, right) => left.page - right.page || left.id.localeCompare(right.id));
if (!cases.length) throw new Error('No source-bound annotation cases were found.');

const repoRoot = fileURLToPath(new URL('../../', import.meta.url));
const runtimeCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repoRoot, encoding: 'utf8' }).trim();
const shadowScript = fileURLToPath(new URL('./pymupdf-shadow.py', import.meta.url));
const shadow = JSON.parse(execFileSync('python3', [
  shadowScript,
  `iitg-utm=${source}`,
  '--strategies', 'lines', 'lines_strict', 'text',
], { cwd: repoRoot, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }));
const document = shadow.documents[0];
if (document.sha256 !== sourceSha256) throw new Error('PyMuPDF source fingerprint mismatch.');
const pageCandidates = new Map();
for (const [strategy, result] of Object.entries(document.strategies)) {
  for (const candidate of result.candidates) {
    const page = Number(candidate.id.match(/:page:(\d+):/)?.[1]);
    if (!page) continue;
    const bbox = candidate.bbox;
    const list = pageCandidates.get(`${strategy}:${page}`) ?? [];
    list.push({ x: bbox[0], y: bbox[1], width: bbox[2] - bbox[0], height: bbox[3] - bbox[1] });
    pageCandidates.set(`${strategy}:${page}`, list);
  }
}

const strategies = Object.keys(document.strategies);
const measuredCases = cases.map((item) => {
  const expected = item.bounds;
  const sourceArea = expected.width * expected.height;
  const byStrategy = {};
  for (const strategy of strategies) {
    const candidates = pageCandidates.get(`${strategy}:${item.page}`) ?? [];
    let best = { coverage: 0, candidateAreaRatio: null };
    for (const candidate of candidates) {
      const coverage = sourceArea > 0 ? intersectionArea(expected, candidate) / sourceArea : 0;
      if (coverage > best.coverage) best = {
        coverage,
        candidateAreaRatio: sourceArea > 0 ? candidate.width * candidate.height / sourceArea : null,
      };
    }
    byStrategy[strategy] = {
      pageCandidateCount: candidates.length,
      bestSourceCoverage: Math.round(best.coverage * 1000) / 1000,
      bestCandidateAreaRatio: best.candidateAreaRatio === null ? null : Math.round(best.candidateAreaRatio * 1000) / 1000,
    };
  }
  return { caseId: item.id, page: item.page, byStrategy };
});

const strategySummary = Object.fromEntries(strategies.map((strategy) => [strategy, {
  ...summarize(measuredCases.map((item) => item.byStrategy[strategy].bestSourceCoverage)),
  medianBestCandidateAreaRatio: (() => {
    const values = measuredCases.map((item) => item.byStrategy[strategy].bestCandidateAreaRatio).filter(Number.isFinite).sort((a, b) => a - b);
    return values.length ? Math.round(values[Math.floor(values.length / 2)] * 1000) / 1000 : null;
  })(),
}]));
const result = {
  schemaVersion: 1,
  runDate: new Date().toISOString().slice(0, 10),
  sourceDocumentId: document.id,
  sourceSha256,
  sourcePageCount: document.pages,
  runtimeCommit,
  pymupdfVersion: shadow.pymupdfVersion,
  annotationArtifacts: annotationPaths,
  annotationAdjudication: 'assistant-reviewed; independent human adjudication pending',
  comparisonKind: 'maximum table-candidate intersection divided by annotated source-bound area',
  sourceTextIncluded: false,
  sourceBoundsIncluded: false,
  annotationCount: cases.length,
  strategySummary,
  cases: measuredCases,
  limitations: [
    'This measures whether a parser candidate envelope intersects an annotated text bound, not whether the table or obligation was correctly extracted.',
    'A full-page candidate can cover many source bounds while being structurally uninformative; candidate area ratios make this overcoverage visible.',
    'Annotations are partial assistant-reviewed regions, not human-adjudicated gold labels.',
    'No candidate bound is negative evidence for prose, OCR, or regions outside the annotation set.',
    'PyMuPDF candidate geometries and source annotation bounds use PDF point coordinates; the production PDF.js parser is not evaluated by this script.',
  ],
};
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
