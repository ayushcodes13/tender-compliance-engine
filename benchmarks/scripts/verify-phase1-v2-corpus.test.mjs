import test from "node:test";
import assert from "node:assert/strict";
import { countTextBearingPages, pageCountFromPdfInfo, validateManifest } from "./verify-phase1-v2-corpus.mjs";

function makeManifest() {
  return {
    schemaVersion: 1,
    inventoryMethod: { sourceContentStored: false },
    splitPolicy: { validation: [], lockedEvaluation: [] },
    documents: [
      { fileName: "copy-a.pdf", split: "development", familyGroupId: "same-tender-family", sha256: "a".repeat(64), bytes: 10 },
      { fileName: "copy-b.pdf", split: "development", familyGroupId: "same-tender-family", sha256: "b".repeat(64), bytes: 10 },
    ],
    previouslyUsedExternalTenders: [],
  };
}

test("corpus manifest keeps related PDF copies in one development family", () => {
  assert.doesNotThrow(() => validateManifest(makeManifest(), ["copy-a.pdf", "copy-b.pdf"]));
});

test("corpus manifest rejects moving an already exposed example into an evaluation split", () => {
  const manifest = makeManifest();
  manifest.documents[1].split = "validation";
  assert.throws(() => validateManifest(manifest, ["copy-a.pdf", "copy-b.pdf"]), /must remain in the development split/u);
});

test("corpus manifest does not label a locked set from prior examples", () => {
  const manifest = makeManifest();
  manifest.splitPolicy.lockedEvaluation = ["copy-b.pdf"];
  assert.throws(() => validateManifest(manifest, ["copy-a.pdf", "copy-b.pdf"]), /must not label a validation or locked evaluation set/u);
});

test("page inventory counts only non-empty selectable-text pages", () => {
  assert.equal(countTextBearingPages("text on page one\f\ftext on page three\f", 3), 2);
});

test("page inventory rejects malformed page counts", () => {
  assert.throws(() => pageCountFromPdfInfo("Pages: 0"), /valid page count/u);
  assert.throws(() => countTextBearingPages("page 1\fpage 2", 1), /expected 1/u);
});
