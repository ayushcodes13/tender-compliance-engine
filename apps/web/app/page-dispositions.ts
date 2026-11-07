export type PageRouteClassification = "relevant" | "possibly_relevant" | "excluded";
export type PageRouteDisposition = { page: number; classification: PageRouteClassification; reason: string };

/** Validates model classifications against the exact pages supplied to one routing call. */
export function validatePageDispositions(value: unknown, pageNumbers: number[]): {
  ok: true;
  dispositions: PageRouteDisposition[];
  unresolvedPages: number[];
} | { ok: false } {
  if (!Array.isArray(value)) return { ok: false };
  const allowedPages = new Set(pageNumbers);
  const seen = new Set<number>();
  const dispositions: PageRouteDisposition[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return { ok: false };
    const candidate = item as { page?: unknown; classification?: unknown; reason?: unknown };
    if (!Number.isInteger(candidate.page) || !allowedPages.has(candidate.page as number)
      || seen.has(candidate.page as number)
      || !["relevant", "possibly_relevant", "excluded"].includes(String(candidate.classification))
      || typeof candidate.reason !== "string" || !candidate.reason.trim()) return { ok: false };
    seen.add(candidate.page as number);
    dispositions.push({
      page: candidate.page as number,
      classification: candidate.classification as PageRouteClassification,
      reason: candidate.reason.trim().slice(0, 400),
    });
  }
  return { ok: true, dispositions, unresolvedPages: pageNumbers.filter((page) => !seen.has(page)) };
}
