import test from "node:test";
import assert from "node:assert/strict";
import { classifyCandidateEvidence } from "./candidate-evidence.ts";

test("accepts exact native text only with a verified source location", () => {
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: true, ocrTextMatch: false, visualTranscription: false, hasLocation: true }), "exact");
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: true, ocrTextMatch: false, visualTranscription: false, hasLocation: false }), "page-only");
});

test("OCR text is reviewable visual evidence, not an exact native citation", () => {
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: false, ocrTextMatch: true, visualTranscription: false, hasLocation: true }), "visual-ocr");
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: false, ocrTextMatch: true, visualTranscription: false, hasLocation: false }), "visual-ocr");
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: true, ocrTextMatch: false, visualTranscription: true, hasLocation: true }), "visual-ocr");
});

test("unsupported suggestions and unlocated image hallucinations are never accepted", () => {
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: false, ocrTextMatch: false, visualTranscription: false, hasLocation: true }), null);
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: false, ocrTextMatch: false, visualTranscription: false, hasLocation: false }), null);
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: false, ocrTextMatch: false, visualTranscription: true, hasLocation: false }), null);
  assert.equal(classifyCandidateEvidence({ nativeTextMatch: false, ocrTextMatch: false, visualTranscription: true, hasLocation: true }), "visual-ocr");
});
