export type VisualPageBatchCandidate = Record<string, unknown> & { visual_region_index: number; page: number };
export type VisualPageBatchEntry = {
  page: number;
  columns: unknown[];
  requirements: VisualPageBatchCandidate[];
};

export function groupVisualPages<T>(pages: T[], maxPagesPerBatch = 2): T[][] {
  if (!Number.isInteger(maxPagesPerBatch) || maxPagesPerBatch < 1) throw new Error("Visual page batch size must be a positive integer.");
  const batches: T[][] = [];
  for (let offset = 0; offset < pages.length; offset += maxPagesPerBatch) batches.push(pages.slice(offset, offset + maxPagesPerBatch));
  return batches;
}

export function validateVisualPageBatchResponse(
  value: unknown,
  expectedPages: number[],
  options: { requireColumns: boolean; maxRegionIndex?: number },
): { ok: true; pages: VisualPageBatchEntry[] } | { ok: false } {
  if (!value || typeof value !== "object" || !Array.isArray((value as { page_results?: unknown }).page_results)) return { ok: false };
  const rawPages = (value as { page_results: unknown[] }).page_results;
  if (rawPages.length !== expectedPages.length) return { ok: false };
  const expected = new Set(expectedPages);
  const seen = new Set<number>();
  const pages: VisualPageBatchEntry[] = [];
  for (const raw of rawPages) {
    if (!raw || typeof raw !== "object") return { ok: false };
    const pageResult = raw as { page?: unknown; columns?: unknown; requirements?: unknown };
    if (!Number.isInteger(pageResult.page) || !expected.has(pageResult.page as number) || seen.has(pageResult.page as number)) return { ok: false };
    if (options.requireColumns && !Array.isArray(pageResult.columns)) return { ok: false };
    if (!Array.isArray(pageResult.requirements)) return { ok: false };
    const requirements: VisualPageBatchCandidate[] = [];
    for (const rawCandidate of pageResult.requirements) {
      if (!rawCandidate || typeof rawCandidate !== "object") return { ok: false };
      const candidate = rawCandidate as Record<string, unknown>;
      if (!Number.isInteger(candidate.visual_region_index)
        || (candidate.visual_region_index as number) < 0
        || (candidate.visual_region_index as number) > (options.maxRegionIndex ?? 2)) return { ok: false };
      requirements.push({ ...candidate, visual_region_index: candidate.visual_region_index as number, page: pageResult.page as number });
    }
    seen.add(pageResult.page as number);
    pages.push({
      page: pageResult.page as number,
      columns: Array.isArray(pageResult.columns) ? pageResult.columns : [],
      requirements,
    });
  }
  if (seen.size !== expected.size || expectedPages.some((page) => !seen.has(page))) return { ok: false };
  return { ok: true, pages };
}
