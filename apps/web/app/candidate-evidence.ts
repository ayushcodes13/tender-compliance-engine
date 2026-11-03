/** Evidence states for the final candidate acceptance gate.
 * "page-only" means the literal quote occurs on the selected native-text
 * page, but no trustworthy highlight can be attached to that quote.
 * It is NEVER an exact visual-location claim. */
export type CandidateEvidencePrecision = "exact" | "visual-ocr" | "page-only";

export function classifyCandidateEvidence(input: {
  nativeTextMatch: boolean;
  ocrTextMatch: boolean;
  visualTranscription: boolean;
  hasLocation: boolean;
}): CandidateEvidencePrecision | null {
  // Image-generated text needs identifiable visual evidence. An OCR transcript
  // match is independently page-grounded, but still requires visual review.
  if (input.visualTranscription) {
    return input.hasLocation || input.ocrTextMatch ? "visual-ocr" : null;
  }
  if (input.ocrTextMatch) return "visual-ocr";
  if (input.nativeTextMatch) return input.hasLocation ? "exact" : "page-only";
  // A model-suggested passage with no source support never reaches the sheet.
  return null;
}
