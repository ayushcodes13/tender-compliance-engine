/** Only associate parser element IDs with the citation shown on the current page.
 * Coverage-source rows are not equivalent to the last selected requirement. */
export function visibleCitationEvidence(
  active: { page: number; sourceReference?: { sourceElementIds?: string[]; locationPrecision?: string } } | null,
  currentPage: number,
  coverageFocusPage?: number,
): { sourceElementIds: string[]; approximate: boolean } | null {
  if (!active || active.page !== currentPage || coverageFocusPage === currentPage) return null;
  return {
    sourceElementIds: active.sourceReference?.sourceElementIds ?? [],
    approximate: active.sourceReference?.locationPrecision === "approximate",
  };
}
