import type { RoutedSection } from "./page-routing";

/** Routing uses both transcripts; neither is relabelled as native evidence. */
export function combinePageTranscripts(nativeText: string, ocrText: string): string {
  return [nativeText.trim(), ocrText.trim()].filter(Boolean).join("\n");
}

/** Prose outside a schedule must not be interpreted as that schedule's left cell. */
export function useComplianceSheetLayout(sections: RoutedSection[], selectedPages: number[]): boolean {
  const schedules = sections.filter((section) => section.section_type === "compliance_schedule");
  return selectedPages.length > 0 && selectedPages.every((page) => schedules.some((section) =>
    page >= section.start_page && page <= section.end_page));
}

/** Bound text and image counts, with overlap so clauses crossing a text window can survive. */
export function buildExtractionBatches(
  pages: Array<{ page: number; text: string }>,
  maxCharacters = 16_000,
  maxPages = 3,
): Array<{ input: string; pageNumbers: number[] }> {
  if (!Number.isInteger(maxCharacters) || maxCharacters < 200 || !Number.isInteger(maxPages) || maxPages < 1) {
    throw new Error("Invalid extraction batch limits.");
  }
  const overlap = Math.min(1_000, Math.floor(maxCharacters / 5));
  const windows: Array<{ page: number; text: string }> = [];
  for (const page of pages) {
    for (let start = 0; start < page.text.length;) {
      const end = Math.min(page.text.length, start + maxCharacters - 100);
      windows.push({ page: page.page, text: page.text.slice(start, end) });
      if (end === page.text.length) break;
      start = end - overlap;
    }
  }
  const batches: Array<{ input: string; pageNumbers: number[] }> = [];
  for (const window of windows) {
    const entry = `PDF PAGE ${window.page}\n${window.text}`;
    const previous = batches.at(-1);
    if (previous && previous.input.length + entry.length + 2 <= maxCharacters
      && new Set([...previous.pageNumbers, window.page]).size <= maxPages) {
      previous.input += `\n\n${entry}`;
      if (!previous.pageNumbers.includes(window.page)) previous.pageNumbers.push(window.page);
    } else batches.push({ input: entry, pageNumbers: [window.page] });
  }
  return batches;
}
