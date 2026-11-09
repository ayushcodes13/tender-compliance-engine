#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

const FORBIDDEN_KEYS = new Set([
  "sourceText", "ocrText", "transcript", "quote", "prompt", "response",
  "bbox", "boundingBox", "coordinates", "image", "pageImage",
]);

function assertSourceFree(value, location = "$") {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertSourceFree(item, `${location}[${index}]`));
    return;
  }
  if (!isObject(value)) return;
  for (const [key, child] of Object.entries(value)) {
    assert(!FORBIDDEN_KEYS.has(key), `Forbidden source material/geometry at ${location}.${key}.`);
    assertSourceFree(child, `${location}.${key}`);
  }
}

function expandRanges(ranges, expectedPages, documentId) {
  assert(Array.isArray(ranges), `${documentId}: reviewed page ranges are missing.`);
  const pages = [];
  let previousEnd = 0;
  for (const range of ranges) {
    assert(Array.isArray(range) && range.length === 2, `${documentId}: invalid page range.`);
    const [start, end] = range;
    assert(Number.isInteger(start) && Number.isInteger(end) && start > previousEnd && end >= start, `${documentId}: page ranges overlap, are unordered, or invalid.`);
    for (let page = start; page <= end; page += 1) pages.push(page);
    previousEnd = end;
  }
  assert(pages.length === expectedPages, `${documentId}: visual skim page count does not match the physical page count.`);
  assert(pages.every((page, index) => page === index + 1), `${documentId}: visual skim ranges omit or reorder physical pages.`);
  return pages;
}

export function verifyVisualReview(manifest, artifact) {
  assert(artifact?.schemaVersion === 1, "Unsupported visual-review schema version.");
  assert(artifact.corpusId === manifest.corpusId, "Visual-review corpus ID does not match the manifest.");
  assert(artifact.reviewLevel === "thumbnail-page-skim", "Visual-review level must remain explicitly page-thumbnail-only.");
  assert(artifact.independentReview === "pending", "Visual review must not be represented as independently adjudicated.");
  assert(artifact.modelCalls === 0, "This visual-review record must not claim model calls.");
  assert(artifact.sourceTextStored === false && artifact.ocrTextStored === false, "Visual-review record must not store source/OCR text.");
  assert(artifact.pageImagesStored === false && artifact.sourceGeometryStored === false, "Visual-review record must not store page images or source geometry.");
  assert(Array.isArray(artifact.unresolvedStructure) && artifact.unresolvedStructure.length > 0, "Unresolved structure must remain explicit.");
  assertSourceFree(artifact);
  assert(Array.isArray(artifact.documents) && artifact.documents.length === manifest.documents.length, "Visual-review record must cover every manifest document.");

  const byId = new Map(artifact.documents.map((document) => [document.id, document]));
  assert(byId.size === artifact.documents.length, "Visual-review record has duplicate document IDs.");
  let pageCount = 0;
  for (const expected of manifest.documents) {
    const document = byId.get(expected.id);
    assert(document, `${expected.id}: no visual-review record found.`);
    assert(document.sha256 === expected.sha256, `${expected.id}: source fingerprint mismatch.`);
    assert(document.physicalPages === expected.physicalPages, `${expected.id}: physical page count mismatch.`);
    pageCount += expandRanges(document.reviewedPageRanges, expected.physicalPages, expected.id).length;
    assert(Array.isArray(document.observations), `${expected.id}: observations must be an array, even when empty.`);
    assert(Array.isArray(document.unknowns) && document.unknowns.length > 0, `${expected.id}: page-level skim must retain unresolved structural questions.`);
    for (const observation of document.observations) {
      assert(isObject(observation) && Array.isArray(observation.pages) && observation.pages.length > 0, `${expected.id}: observation needs physical page references.`);
      assert(observation.pages.every((page) => Number.isInteger(page) && page >= 1 && page <= expected.physicalPages), `${expected.id}: observation references a page outside the source document.`);
      assert(typeof observation.kind === "string" && /^[a-z0-9-]+$/u.test(observation.kind), `${expected.id}: observation kind must be a source-free controlled label.`);
      assert(["visual-candidate", "render-confirmed-single-reviewer"].includes(observation.evidenceLevel), `${expected.id}: observation evidence level is unsupported or overclaimed.`);
    }
  }
  assert(artifact.documents.every((document) => byId.has(document.id)), "Visual-review record contains documents outside the manifest.");
  return { passed: true, corpusId: artifact.corpusId, documents: artifact.documents.length, physicalPages: pageCount, observations: artifact.documents.reduce((sum, document) => sum + document.observations.length, 0), independentReview: artifact.independentReview, reviewLevel: artifact.reviewLevel };
}

async function main() {
  const [manifestPath = "benchmarks/phase-1-v2-corpus.json", artifactPath = "benchmarks/phase-1-v2-visual-review.json"] = process.argv.slice(2);
  const manifest = JSON.parse(await readFile(resolve(manifestPath), "utf8"));
  const artifact = JSON.parse(await readFile(resolve(artifactPath), "utf8"));
  process.stdout.write(`${JSON.stringify(verifyVisualReview(manifest, artifact))}\n`);
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Visual-review verification failed."}\n`);
    process.exitCode = 1;
  });
}
