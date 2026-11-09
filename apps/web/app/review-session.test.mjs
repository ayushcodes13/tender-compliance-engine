import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { decryptReviewSession, encryptReviewSession, MAX_REVIEW_SESSION_FILE_BYTES, verifyReviewSessionSource } from "./review-session.ts";

const identity = {
  documentFingerprint: "a".repeat(64),
  filename: "tender.pdf",
};

function snapshot() {
  return {
    analysis: {
      filename: identity.filename,
      pageCount: 1,
      document: {
        documentId: `doc-${identity.documentFingerprint.slice(0, 24)}`,
        documentVersionId: `ver-${identity.documentFingerprint}`,
        documentFingerprint: identity.documentFingerprint,
        pageCount: 1,
      },
      requirements: [{
        id: "req-1",
        text: "Source backed requirement",
        quote: "Source backed requirement",
        page: 1,
        reviewed: true,
        sourceReference: {
          documentId: `doc-${identity.documentFingerprint.slice(0, 24)}`,
          documentVersionId: `ver-${identity.documentFingerprint}`,
          documentFingerprint: identity.documentFingerprint,
          physicalPdfPageNumber: 1,
          sourceText: "Source backed requirement",
          sourceElementIds: ["text-1"],
          locationPrecision: "exact",
          bboxCoordinateSystem: "pdfjs-viewport-scale-1",
          bbox: { x: 10, y: 10, width: 10, height: 5 },
        },
      }],
    },
    responseSheet: {
      columns: [{ header: "Requirement", role: "requirement" }],
      rows: [{ id: "row-1", sourceRequirementId: "req-1", sourceRequirementIds: ["req-1"], values: ["Source backed requirement"] }],
    },
    sheetEdited: true,
  };
}

test("encrypted session restores review edits while preserving tender identity", async () => {
  const encrypted = await encryptReviewSession(snapshot(), "a memorable client passphrase", identity);
  assert.equal(encrypted.type, "application/vnd.tender-review-session+json");
  const restored = await decryptReviewSession(new File([encrypted], "review.tce-review"), "a memorable client passphrase");
  assert.equal(restored.documentFingerprint, identity.documentFingerprint);
  assert.equal(restored.analysis.requirements[0].reviewed, true);
  assert.equal(restored.responseSheet.rows[0].values[0], "Source backed requirement");
  assert.equal(restored.sheetEdited, true);
  assert.ok(!await encrypted.text().then((text) => text.includes("Source backed requirement")));
});

test("wrong passphrase and modified ciphertext cannot restore a session", async () => {
  const encrypted = await encryptReviewSession(snapshot(), "a memorable client passphrase", identity);
  await assert.rejects(
    decryptReviewSession(new File([encrypted], "review.tce-review"), "a different client passphrase"),
    /incorrect or the review session file was changed/,
  );
  const envelope = JSON.parse(await encrypted.text());
  envelope.ciphertext = `${envelope.ciphertext.startsWith("A") ? "B" : "A"}${envelope.ciphertext.slice(1)}`;
  const changed = new File([JSON.stringify(envelope)], "review.tce-review");
  await assert.rejects(decryptReviewSession(changed, "a memorable client passphrase"), /incorrect or the review session file was changed/);
});

test("rejects weak passphrases and review sessions without valid source identity", async () => {
  await assert.rejects(encryptReviewSession(snapshot(), "short", identity), /between 12 and 512/);
  const invalid = snapshot();
  invalid.analysis.document.documentFingerprint = "not-a-sha256";
  await assert.rejects(encryptReviewSession(invalid, "a memorable client passphrase", identity), /missing valid tender identity/);
  assert.equal(MAX_REVIEW_SESSION_FILE_BYTES, 90 * 1024 * 1024);
});

test("restores citation access only for the PDF bytes matching the saved fingerprint", async () => {
  const original = new Blob(["source PDF bytes"]);
  const fingerprint = createHash("sha256").update("source PDF bytes").digest("hex");
  assert.equal(await verifyReviewSessionSource(original, fingerprint), true);
  assert.equal(await verifyReviewSessionSource(new Blob(["visually similar but different PDF"]), fingerprint), false);
  assert.equal(await verifyReviewSessionSource(original, "untrusted"), false);
});
