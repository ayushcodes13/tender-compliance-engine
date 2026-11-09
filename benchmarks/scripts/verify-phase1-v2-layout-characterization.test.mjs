import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { verifyLayoutCharacterization } from "./verify-phase1-v2-layout-characterization.mjs";

const manifest = JSON.parse(await readFile(new URL("../phase-1-v2-corpus.json", import.meta.url), "utf8"));
const artifact = JSON.parse(await readFile(new URL("../phase-1-v2-layout-characterization.json", import.meta.url), "utf8"));

test("reconciles every page, OCR disposition, image region, and source-free aggregate", () => {
  const result = verifyLayoutCharacterization(manifest, artifact);
  assert.equal(result.physicalPages, 367);
  assert.equal(result.parserInventoryIssues, 0);
  assert.equal(result.modelCalls, 0);
  assert.equal(result.sourceTextStored, false);
});

test("rejects a missing physical page even when aggregate claims remain unchanged", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].pages.shift();
  assert.throws(() => verifyLayoutCharacterization(manifest, changed), /page coverage does not match/u);
});

test("rejects selected regions with no attempt or skip reason", () => {
  const changed = structuredClone(artifact);
  const page = changed.documents.flatMap((document) => document.pages).find((entry) => entry.imageRegions.some((region) => region.targeted));
  const region = page.imageRegions.find((entry) => entry.targeted);
  region.disposition = "not-attempted";
  delete region.skipReason;
  assert.throws(() => verifyLayoutCharacterization(manifest, changed), /skipped region OCR needs a reason/u);
});

test("rejects persisted source or OCR transcript fields", () => {
  const changed = structuredClone(artifact);
  changed.documents[0].pages[0].ocrText = "must not persist";
  assert.throws(() => verifyLayoutCharacterization(manifest, changed), /Forbidden source-content/u);
});
