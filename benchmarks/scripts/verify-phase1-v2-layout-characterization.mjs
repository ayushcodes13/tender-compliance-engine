#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { summarizeLayoutCharacterization } from "./characterize-phase1-v2-layout.mjs";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function sortedEntries(value) {
  return Object.entries(value).sort(([left], [right]) => left.localeCompare(right));
}

export function verifyLayoutCharacterization(manifest, artifact) {
  assert(artifact?.schemaVersion === 1, "Unsupported layout-characterization schema version.");
  assert(artifact.corpusId === manifest.corpusId, "Characterization corpus ID does not match the manifest.");
  assert(artifact.sourceTextStored === false && artifact.ocrTextStored === false && artifact.boundingBoxesStored === false, "Characterization must not store document text or source geometry.");
  assert(artifact.modelCalls === 0, "This local characterization must not call a model.");
  assert(Array.isArray(artifact.documents) && artifact.documents.length === manifest.documents.length, "Every manifest PDF must have one document characterization.");

  const forbiddenKeys = new Set(["sourceText", "ocrText", "transcript", "quote", "prompt", "response", "bbox", "boundingBox"]);
  const inspectForForbiddenKeys = (value, location = "$") => {
    if (Array.isArray(value)) {
      value.forEach((item, index) => inspectForForbiddenKeys(item, `${location}[${index}]`));
      return;
    }
    if (!isObject(value)) return;
    for (const [key, child] of Object.entries(value)) {
      assert(!forbiddenKeys.has(key), `Forbidden source-content/geometry field at ${location}.${key}.`);
      inspectForForbiddenKeys(child, `${location}.${key}`);
    }
  };
  inspectForForbiddenKeys(artifact);

  const documents = new Map(artifact.documents.map((document) => [document.id, document]));
  assert(documents.size === artifact.documents.length, "Characterization has duplicate document IDs.");
  for (const expected of manifest.documents) {
    const document = documents.get(expected.id);
    assert(document, `${expected.id}: no document characterization found.`);
    assert(document.sha256 === expected.sha256 && document.physicalPages === expected.physicalPages, `${expected.id}: source fingerprint/page count mismatch.`);
    assert(Array.isArray(document.pages) && document.pages.length === expected.physicalPages, `${expected.id}: page coverage does not match the source page count.`);
    assert(Number.isInteger(document.sourceInventoryIssueCount) && document.sourceInventoryIssueCount >= 0, `${expected.id}: parser inventory issue count is missing.`);
    assert(isObject(document.sourceInventoryIssueCodes), `${expected.id}: parser inventory issue summary is missing.`);

    const pageIssueCounts = {};
    for (const [index, page] of document.pages.entries()) {
      const physicalPage = index + 1;
      assert(page.physicalPage === physicalPage, `${expected.id}: physical page sequence is missing/reordered at page ${physicalPage}.`);
      assert(["not-recommended", "not-attempted", "text-found", "no-text-found", "failed"].includes(page.ocrStatus), `${expected.id} p.${physicalPage}: invalid OCR page status.`);
      assert(typeof page.ocrAttempted === "boolean" && page.ocrExecuted === page.ocrAttempted, `${expected.id} p.${physicalPage}: OCR attempt flags disagree.`);
      assert(["none", "full-page", "image-regions"].includes(page.ocrInputMode), `${expected.id} p.${physicalPage}: invalid OCR input mode.`);
      if (page.ocrStatus === "not-recommended") assert(!page.ocrAttempted && page.ocrInputMode === "none", `${expected.id} p.${physicalPage}: not-recommended OCR has attempt data.`);
      if (page.ocrStatus === "not-attempted") assert(!page.ocrAttempted && typeof page.ocrSkipReason === "string", `${expected.id} p.${physicalPage}: skipped OCR needs an explicit reason.`);
      if (["text-found", "no-text-found", "failed"].includes(page.ocrStatus)) assert(page.ocrAttempted, `${expected.id} p.${physicalPage}: completed/failed OCR lacks an attempt.`);
      assert(Number.isInteger(page.ocrLineCount) && page.ocrLineCount >= 0 && Number.isInteger(page.ocrWordCount) && page.ocrWordCount >= 0, `${expected.id} p.${physicalPage}: OCR count metrics are invalid.`);

      assert(Number.isInteger(page.imageRegionCount) && Array.isArray(page.imageRegions) && page.imageRegions.length === page.imageRegionCount, `${expected.id} p.${physicalPage}: image regions are not fully enumerated.`);
      const regionIds = new Set();
      for (const [regionIndex, region] of page.imageRegions.entries()) {
        assert(region.index === regionIndex, `${expected.id} p.${physicalPage}: image-region indices are missing/reordered.`);
        assert(typeof region.id === "string" && region.id.trim() && !regionIds.has(region.id), `${expected.id} p.${physicalPage}: image-region ID is invalid or duplicated.`);
        regionIds.add(region.id);
        assert(typeof region.targeted === "boolean", `${expected.id} p.${physicalPage}: image-region targeting state is missing.`);
        assert(["not-targeted", "not-attempted", "text-found", "no-text-found", "failed"].includes(region.disposition), `${expected.id} p.${physicalPage}: invalid image-region disposition.`);
        if (region.disposition === "not-targeted") assert(!region.targeted, `${expected.id} p.${physicalPage}: not-targeted region is marked targeted.`);
        if (region.targeted && region.disposition === "not-attempted") assert(typeof region.skipReason === "string", `${expected.id} p.${physicalPage}: skipped region OCR needs a reason.`);
        if (region.disposition === "text-found") assert(page.ocrStatus === "text-found", `${expected.id} p.${physicalPage}: region text found but page is not marked text-found.`);
      }
      assert(Array.isArray(page.sourceInventoryIssueCodes), `${expected.id} p.${physicalPage}: structural issue codes are missing.`);
      for (const code of page.sourceInventoryIssueCodes) pageIssueCounts[code] = (pageIssueCounts[code] ?? 0) + 1;
    }
    assert(JSON.stringify(sortedEntries(pageIssueCounts)) === JSON.stringify(sortedEntries(document.sourceInventoryIssueCodes)), `${expected.id}: per-page and document parser-issue counts disagree.`);
    assert(document.sourceInventoryIssueCount === Object.values(pageIssueCounts).reduce((sum, count) => sum + count, 0), `${expected.id}: parser issue total does not reconcile.`);
  }

  const summary = summarizeLayoutCharacterization(artifact.documents);
  assert(JSON.stringify(summary) === JSON.stringify(artifact.summary), "Aggregate characterization summary does not reconcile to the page records.");
  return { passed: true, corpusId: artifact.corpusId, ...summary };
}

async function main() {
  const [manifestPath = "benchmarks/phase-1-v2-corpus.json", artifactPath = "benchmarks/phase-1-v2-layout-characterization.json"] = process.argv.slice(2);
  const manifest = JSON.parse(await readFile(resolve(manifestPath), "utf8"));
  const artifact = JSON.parse(await readFile(resolve(artifactPath), "utf8"));
  process.stdout.write(`${JSON.stringify(verifyLayoutCharacterization(manifest, artifact))}\n`);
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : "Layout characterization verification failed."}\n`);
    process.exitCode = 1;
  });
}
