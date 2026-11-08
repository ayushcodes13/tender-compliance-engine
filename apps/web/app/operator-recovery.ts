import type { RequirementSourceReference } from "./source-document";

type DocumentIdentity = Pick<RequirementSourceReference,
  "documentId" | "documentVersionId" | "documentFingerprint">;

/** Insert a recovered requirement beside its physical source page while
 * preserving the existing extraction order for items on that same page. */
export function insertRequirementByPhysicalPage<T extends { page: number }>(
  requirements: readonly T[],
  requirement: T,
): T[] {
  const insertIndex = requirements.findIndex((existing) => existing.page > requirement.page);
  return insertIndex < 0
    ? [...requirements, requirement]
    : [...requirements.slice(0, insertIndex), requirement, ...requirements.slice(insertIndex)];
}

export type OperatorAddedRequirement = {
  id: string;
  text: string;
  quote: string;
  page: number;
  category: string;
  parameter?: string;
  sourceSectionTitle?: string;
  headingPrefix?: string;
  rowType: "requirement";
  precision: "page-only";
  verdict: "needs_human_review";
  needsHumanReview: true;
  reviewed: false;
  isOperatorAdded: true;
  bbox: null;
  sourceReference: RequirementSourceReference;
};

/** Keep an operator's source transcription separate from parser-owned evidence. */
export function createOperatorAddedRequirement(input: {
  id: string;
  page: number;
  text: string;
  category: string;
  heading?: string;
  document: DocumentIdentity;
}): OperatorAddedRequirement {
  const text = input.text.trim();
  const heading = input.heading?.trim() || undefined;
  const sourceReference = createOperatorPageReference(input.document, input.page);

  return {
    id: input.id,
    text,
    quote: text,
    page: input.page,
    category: input.category.trim() || "Technical",
    parameter: heading,
    sourceSectionTitle: heading,
    headingPrefix: heading,
    rowType: "requirement",
    precision: "page-only",
    verdict: "needs_human_review",
    needsHumanReview: true,
    reviewed: false,
    isOperatorAdded: true,
    bbox: null,
    sourceReference: { ...sourceReference, sourceText: text },
  };
}

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
    || !/^[a-f0-9]{64}$/.test(source.documentFingerprint)
    || source.documentId !== `doc-${source.documentFingerprint.slice(0, 24)}`
    || source.documentVersionId !== `ver-${source.documentFingerprint}`) return null;
  return {
    documentId: source.documentId,
    documentVersionId: source.documentVersionId,
    documentFingerprint: source.documentFingerprint,
    pageCount,
    inventoryIntegrity: "unverified",
  };
}
