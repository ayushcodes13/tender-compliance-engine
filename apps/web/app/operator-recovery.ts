import type { RequirementSourceReference } from "./source-document";

type DocumentIdentity = Pick<RequirementSourceReference,
  "documentId" | "documentVersionId" | "documentFingerprint">;

/**
 * A manual row's wording is supplied by the operator, NOT extracted from the
 * PDF. The page is a navigation pointer only; source text, offsets, geometry,
 * and parser IDs must remain absent until a separate source-verification step.
 */
export function createOperatorPageReference(
  document: DocumentIdentity,
  page: number,
): RequirementSourceReference {
  if (!Number.isInteger(page) || page < 1) throw new RangeError("Invalid physical PDF page");
  return {
    documentId: document.documentId,
    documentVersionId: document.documentVersionId,
    documentFingerprint: document.documentFingerprint,
    physicalPdfPageNumber: page,
    sourceText: "",
    sourceElementIds: [],
    bbox: null,
    bboxCoordinateSystem: "pdfjs-viewport-scale-1",
    extractionMethod: "operator-entered",
    locationPrecision: "approximate",
  };
}

/**
 * Recover the original document identity from a genuinely source-linked
 * candidate, not a guessed ID/fingerprint. A failed full analysis has not
 * established a structurally complete source inventory.
 */
export function recoverDocumentIdentity(
  source: RequirementSourceReference,
  pageCount: number,
): {
  documentId: string;
  documentVersionId: string;
  documentFingerprint: string;
  pageCount: number;
  inventoryIntegrity: "unverified";
} | null {
  if (!Number.isInteger(pageCount) || pageCount < 1
    || !Number.isInteger(source.physicalPdfPageNumber) || source.physicalPdfPageNumber < 1
    || source.physicalPdfPageNumber > pageCount
    || !/^doc-[a-f0-9]{24}$/.test(source.documentId)
    || !/^[a-f0-9]{64}$/.test(source.documentFingerprint)
    || source.documentVersionId !== `ver-${source.documentFingerprint}`) return null;
  return {
    documentId: source.documentId,
    documentVersionId: source.documentVersionId,
    documentFingerprint: source.documentFingerprint,
    pageCount,
    inventoryIntegrity: "unverified",
  };
}
