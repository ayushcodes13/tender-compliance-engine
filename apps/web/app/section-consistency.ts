export type PossibleSourceConflict = {
  page_a: number;
  quote_a: string;
  page_b: number;
  quote_b: string;
  reason: string;
};

export type SourceConflictValidation = {
  warnings: string[];
  uncertainPages: number[];
  routedPages: number[];
  rejectedCount: number;
};

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/gu, " ").trim();
}

/** Only reports model-proposed conflicts when both literal quotes occur on their claimed source pages. */
export function validatePossibleSourceConflicts(
  proposals: unknown[],
  sourceTextByPage: Map<number, string>,
): SourceConflictValidation {
  const warnings: string[] = [];
  const uncertainPages = new Set<number>();
  const routedPages = new Set<number>();
  let rejectedCount = 0;

  for (const value of proposals) {
    if (!value || typeof value !== "object") {
      rejectedCount += 1;
      continue;
    }
    const proposal = value as Partial<PossibleSourceConflict>;
    const pageA = proposal.page_a;
    const pageB = proposal.page_b;
    const quoteA = typeof proposal.quote_a === "string" ? normalizeWhitespace(proposal.quote_a) : "";
    const quoteB = typeof proposal.quote_b === "string" ? normalizeWhitespace(proposal.quote_b) : "";
    const reason = typeof proposal.reason === "string" ? normalizeWhitespace(proposal.reason) : "";
    const validPages = Number.isInteger(pageA) && Number.isInteger(pageB)
      && pageA !== pageB && sourceTextByPage.has(pageA!) && sourceTextByPage.has(pageB!);
    if (!validPages) {
      rejectedCount += 1;
      continue;
    }
    uncertainPages.add(pageA!);
    uncertainPages.add(pageB!);
    const sourceA = normalizeWhitespace(sourceTextByPage.get(pageA!) ?? "");
    const sourceB = normalizeWhitespace(sourceTextByPage.get(pageB!) ?? "");
    if (quoteA.length < 8 || quoteB.length < 8 || quoteA.length > 500 || quoteB.length > 500
      || !reason || reason.length > 400 || !sourceA.includes(quoteA) || !sourceB.includes(quoteB)) {
      rejectedCount += 1;
      continue;
    }
    warnings.push(
      `Possible cross-section inconsistency on PDF pages ${pageA} and ${pageB}. Source on page ${pageA}: ${quoteA.slice(0, 180)}. Source on page ${pageB}: ${quoteB.slice(0, 180)}. Model explanation (unverified): ${reason.slice(0, 280)} Inspect both pages; neither source is treated as authoritative.`,
    );
    routedPages.add(pageA!);
    routedPages.add(pageB!);
  }

  return {
    warnings,
    uncertainPages: [...uncertainPages].sort((a, b) => a - b),
    routedPages: [...routedPages].sort((a, b) => a - b),
    rejectedCount,
  };
}
