import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  deleteLocalReviewDraft,
  getLocalReviewDraftSummary,
  loadLocalReviewDraft,
  MAX_LOCAL_DRAFT_FILE_BYTES,
  saveLocalReviewDraft,
} from "./local-review-draft.ts";

class MemoryDraftStorage {
  record;
  async get() { return this.record; }
  async put(record, allowReplacement = false) {
    if (this.record && this.record.documentFingerprint !== record.documentFingerprint && !allowReplacement) {
      throw new Error("A different tender review is already saved in this browser. Confirm replacement before saving this tender.");
    }
    this.record = structuredClone(record);
  }
  async delete() { this.record = undefined; }
}

async function fixture(filename = "tender.pdf") {
  const file = new File([`%PDF-1.4\nsource bytes for ${filename}\n%%EOF`], filename, { type: "application/pdf", lastModified: 1234 });
  const fingerprint = createHash("sha256").update(Buffer.from(await file.arrayBuffer())).digest("hex");
  const documentId = `doc-${fingerprint.slice(0, 24)}`;
  const versionId = `ver-${fingerprint}`;
  const analysis = {
    filename: "tender.pdf",
    pageCount: 2,
    textPages: 2,
    document: { documentId, documentVersionId: versionId, documentFingerprint: fingerprint, pageCount: 2, inventoryIntegrity: "structurally-verified" },
    requirements: [{
      id: "req-1",
      page: 2,
      quote: "Supplier shall provide annual calibration.",
      text: "Annual calibration",
      reviewed: true,
      sourceReference: {
        documentId,
        documentVersionId: versionId,
        documentFingerprint: fingerprint,
        physicalPdfPageNumber: 2,
        sourceText: "Supplier shall provide annual calibration.",
        sourceElementIds: ["p2-block-3"],
        startOffset: 18,
        endOffset: 61,
        locationPrecision: "exact",
      },
    }],
  };
  const responseSheet = {
    columns: [{ header: "Requirement", role: "requirement" }, { header: "OEM response", role: "response" }],
    rows: [{ id: "row-1", sourceRequirementId: "req-1", sourceRequirementIds: ["req-1"], values: ["Edited review wording", "Pending OEM answer"] }],
  };
  return { file, fingerprint, analysis, responseSheet };
}

test("saves and resumes the original file, source identity, reviewer marks, and edited export rows", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  await saveLocalReviewDraft({ ...original, sheetEdited: true, activeRequirementId: "req-1", page: 2 }, storage);
  const restored = await loadLocalReviewDraft(storage);

  assert.ok(restored);
  assert.equal(restored.file.name, "tender.pdf");
  assert.equal(restored.file.size, original.file.size);
  assert.equal(restored.documentFingerprint, original.fingerprint);
  assert.equal(restored.analysis.document.documentFingerprint, original.fingerprint);
  assert.equal(restored.analysis.requirements[0].sourceReference.documentId, original.analysis.document.documentId);
  assert.equal(restored.analysis.requirements[0].sourceReference.physicalPdfPageNumber, 2);
  assert.equal(restored.analysis.requirements[0].sourceReference.sourceText, "Supplier shall provide annual calibration.");
  assert.deepEqual(restored.analysis.requirements[0].sourceReference.sourceElementIds, ["p2-block-3"]);
  assert.equal(restored.analysis.requirements[0].reviewed, true);
  assert.deepEqual(restored.responseSheet, original.responseSheet);
  assert.equal(restored.sheetEdited, true);
  assert.equal(restored.activeRequirementId, "req-1");
  assert.equal(restored.page, 2);
});

test("shows a bounded local-draft summary without exposing tender text", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  await saveLocalReviewDraft({ ...original, sheetEdited: false }, storage);
  const summary = await getLocalReviewDraftSummary(storage);

  assert.equal(summary.filename, "tender.pdf");
  assert.equal(summary.pageCount, 2);
  assert.equal(summary.fileBytes, original.file.size);
  assert.equal("sourceText" in summary, false);
  assert.equal("quote" in summary, false);
});

test("refuses to restore if saved PDF bytes no longer match the analyzed document fingerprint", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  await saveLocalReviewDraft({ ...original, sheetEdited: false }, storage);
  storage.record.fileBlob = new Blob(["different PDF bytes"]);
  await assert.rejects(loadLocalReviewDraft(storage), /does not match this tender file/i);
});

test("refuses to restore if a requirement citation points to a different document", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  await saveLocalReviewDraft({ ...original, sheetEdited: false }, storage);
  storage.record.analysis.requirements[0].sourceReference.documentId = "doc-another-tender";
  await assert.rejects(loadLocalReviewDraft(storage), /citation does not match the tender identity/i);
});

test("refuses to save analysis bound to a different tender identity", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  original.analysis.document.documentFingerprint = "0".repeat(64);
  await assert.rejects(saveLocalReviewDraft({ ...original, sheetEdited: false }, storage), /does not match this tender file/i);
  assert.equal(storage.record, undefined);
});

test("refuses to save response rows linked to requirements outside the analyzed tender", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  original.responseSheet.rows[0].sourceRequirementIds = ["req-from-another-analysis"];
  await assert.rejects(
    saveLocalReviewDraft({ ...original, sheetEdited: true }, storage),
    /citation outside this analysis/i,
  );
  assert.equal(storage.record, undefined);
});

test("refuses to restore a saved response row whose source requirement was removed or changed", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  await saveLocalReviewDraft({ ...original, sheetEdited: true }, storage);
  storage.record.responseSheet.rows[0].sourceRequirementId = "req-from-another-analysis";
  await assert.rejects(loadLocalReviewDraft(storage), /missing source requirement/i);
});

test("rejects local tender files above the 32 MiB storage bound", async () => {
  const storage = new MemoryDraftStorage();
  const file = new File([new Uint8Array(MAX_LOCAL_DRAFT_FILE_BYTES + 1)], "too-large.pdf", { type: "application/pdf" });
  await assert.rejects(saveLocalReviewDraft({ file, analysis: {}, responseSheet: {}, sheetEdited: false }, storage), /up to 32 MiB/i);
  assert.equal(storage.record, undefined);
});

test("does not overwrite a different saved tender without explicit replacement", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture("first.pdf");
  const replacement = await fixture("second.pdf");
  await saveLocalReviewDraft({ ...original, sheetEdited: false }, storage);
  await assert.rejects(saveLocalReviewDraft({ ...replacement, sheetEdited: false }, storage), /Confirm replacement/i);
  assert.equal((await getLocalReviewDraftSummary(storage)).filename, "first.pdf");
  await saveLocalReviewDraft({ ...replacement, sheetEdited: false, replaceExisting: true }, storage);
  assert.equal((await getLocalReviewDraftSummary(storage)).filename, "second.pdf");
});

test("rejects an unsupported local-draft schema without overwriting it", async () => {
  const storage = new MemoryDraftStorage();
  storage.record = { id: "active", schemaVersion: 999 };
  await assert.rejects(loadLocalReviewDraft(storage), /unsupported format/i);
  assert.equal(storage.record.schemaVersion, 999);
});

test("deletes only the single local review draft when requested", async () => {
  const storage = new MemoryDraftStorage();
  const original = await fixture();
  await saveLocalReviewDraft({ ...original, sheetEdited: false }, storage);
  await deleteLocalReviewDraft(storage);
  assert.equal(await getLocalReviewDraftSummary(storage), null);
});
