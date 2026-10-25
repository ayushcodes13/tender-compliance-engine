export type RoutingPage = {
  page: number;
  text: string;
  rawText?: string;
  routingText?: string;
  hasVectorTableGeometry?: boolean;
};

export type RoutedSection = {
  title: string;
  start_page: number;
  end_page: number;
  section_type: "technical_requirements" | "compliance_schedule";
  reason: string;
};

export type RoutingBatch = {
  pages: RoutingPage[];
  input: string;
  clippedPages: number[];
};

const PAGE_SUMMARY_LIMIT = 900;
export const ROUTING_BATCH_CHARACTER_LIMIT = 10_000;

const technicalSignal = /\b(?:technical|specification|equipment|instrument|machine|system|parameter|performance|capacity|accuracy|resolution|range|voltage|current|power|pressure|temperature|dimension|material|shall|must|required|minimum|maximum|at least|not less than|comply|conform|test|calibration|compliance|remark|deviation)\b/i;
const measuredValue = /(?:\b\d+(?:[.,]\d+)?\s*(?:%|mm|cm|m|µm|nm|hz|khz|mhz|ghz|v|kv|a|ma|w|kw|n|kn|kg|g|°c|°f|bar|mpa|rpm|db)\b|[<>≤≥±])/i;
const sectionSignal = /\b(?:annex(?:ure)?|appendix|technical|compliance|specification|schedule|equipment|requirements?)\b/i;

function normalizedLine(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function scoreLine(line: string, index: number): number {
  return (index < 3 ? 2 : 0)
    + (sectionSignal.test(line) ? 6 : 0)
    + (technicalSignal.test(line) ? 5 : 0)
    + (measuredValue.test(line) ? 5 : 0)
    + (/\b(?:s\.?\s*no\.?|description|parameter|quantity|remarks?|deviation|compliance)\b/i.test(line) ? 3 : 0);
}

function excerptForPage(page: RoutingPage): { summary: string; clipped: boolean } {
  const original = page.routingText?.trim() || page.rawText?.trim() || page.text.trim();
  const lines = original.split(/\r?\n/).map(normalizedLine).filter(Boolean);
  const candidates = lines.map((line, index) => ({ line, index, score: scoreLine(line, index) }));
  const selected = new Set<number>();

  for (const candidate of candidates.slice(0, 2)) selected.add(candidate.index);
  for (const candidate of [...candidates]
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, 5)) selected.add(candidate.index);

  let summary = [...selected].sort((a, b) => a - b).map((index) => candidates[index].line).join(" | ");
  if (!summary) summary = normalizedLine(original);
  const clipped = summary.length > PAGE_SUMMARY_LIMIT || original.length > summary.length;
  if (summary.length > PAGE_SUMMARY_LIMIT) {
    summary = `${summary.slice(0, PAGE_SUMMARY_LIMIT - 1).replace(/\s+\S*$/, "")}…`;
  }
  return { summary, clipped };
}

export function buildRoutingBatches(
  pages: RoutingPage[],
  maxCharacters = ROUTING_BATCH_CHARACTER_LIMIT,
): RoutingBatch[] {
  const ordered = pages
    .filter((page) => page.text.trim().length > 0 || Boolean(page.rawText?.trim()))
    .slice()
    .sort((a, b) => a.page - b.page)
    .map((page) => ({ page, ...excerptForPage(page) }));
  const batches: RoutingBatch[] = [];
  let index = 0;

  while (index < ordered.length) {
    const start = index;
    let characterCount = 0;
    const items: typeof ordered = [];
    while (index < ordered.length) {
      const item = ordered[index];
      const entry = `PDF PAGE ${item.page.page} (${item.page.text.length} source characters; ${item.page.hasVectorTableGeometry ? "vector table geometry detected" : "no vector table geometry detected"})\n${item.summary}`;
      if (items.length > 0 && characterCount + entry.length > maxCharacters) break;
      items.push(item);
      characterCount += entry.length + 2;
      index += 1;
    }

    batches.push({
      pages: items.map((item) => item.page),
      input: items.map((item) => `PDF PAGE ${item.page.page} (${item.page.text.length} source characters; ${item.page.hasVectorTableGeometry ? "vector table geometry detected" : "no vector table geometry detected"})\n${item.summary}`).join("\n\n"),
      clippedPages: items.filter((item) => item.clipped).map((item) => item.page.page),
    });

    // Let adjacent routing calls both see the shared boundary page so a section
    // that continues across batches is less likely to be cut at the boundary.
    if (index < ordered.length) index = Math.max(start + 1, index - 1);
  }

  return batches;
}

export function expandRoutedSections(sections: RoutedSection[], availablePages: number[]): number[] {
  const available = new Set(availablePages);
  const selected = new Set<number>();
  for (const section of sections) {
    for (let page = section.start_page; page <= section.end_page; page += 1) {
      if (available.has(page)) selected.add(page);
    }
  }
  return [...selected].sort((a, b) => a - b);
}
