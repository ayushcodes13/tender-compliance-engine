export type PositionedTextItem = {
  start: number;
  end: number;
  text: string;
  pdfX: number;
  pdfY: number;
  pdfWidth: number;
  pdfHeight: number;
};

function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function displayLinesForQuote(
  quote: string,
  rawText: string,
  rawItemMap: number[],
  positioned: PositionedTextItem[],
): string[] | null {
  const target = normalize(quote);
  if (!target) return null;
  let searchable = "";
  const rawOffsets: number[] = [];
  let inWhitespace = false;
  for (let i = 0; i < rawText.length; i += 1) {
    const char = rawText[i];
    if (/\s/.test(char)) {
      if (!inWhitespace) {
        searchable += " ";
        rawOffsets.push(i);
      }
      inWhitespace = true;
    } else {
      searchable += char;
      rawOffsets.push(i);
      inWhitespace = false;
    }
  }
  const start = searchable.indexOf(target);
  if (start < 0 || searchable.indexOf(target, start + target.length) >= 0) return null;
  const rawStart = rawOffsets[start];
  const rawEnd = rawOffsets[start + target.length - 1] + 1;
  const used = new Set<number>();
  for (let i = rawStart; i < rawEnd; i += 1) {
    const index = rawItemMap[i];
    if (index !== undefined && index >= 0) used.add(index);
  }
  const items = [...used]
    .map((index) => positioned[index])
    .filter((item) => item && item.text.length > 0)
    .sort((a, b) => b.pdfY - a.pdfY || a.pdfX - b.pdfX);
  if (items.length === 0) return null;
  const tolerance = Math.max(1.5, Math.min(3, Math.max(...items.map((item) => item.pdfHeight)) * 0.3));
  const groups: PositionedTextItem[][] = [];
  for (const item of items) {
    let line = groups.find((group) => Math.abs(group[0].pdfY - item.pdfY) <= tolerance);
    if (!line) groups.push(line = []);
    line.push(item);
  }
  const lines = groups.map((group) => {
    const ordered = group.sort((a, b) => a.pdfX - b.pdfX);
    let line = "";
    let previous: PositionedTextItem | undefined;
    for (const item of ordered) {
      const fragment = rawText.slice(item.start, item.end);
      if (!fragment) continue;
      if (line && previous && !/\s$/.test(line) && !/^\s/.test(fragment)) {
        const gap = item.pdfX - (previous.pdfX + previous.pdfWidth);
        const startsPunctuation = /^[,.;:!?%)\]}]/.test(fragment);
        const followsOpeningPunctuation = /[(\[{]$/.test(line);
        if (!startsPunctuation && !followsOpeningPunctuation && gap >= Math.max(1.5, Math.max(previous.pdfHeight, item.pdfHeight) * 0.18)) {
          line += " ";
        }
      }
      line += fragment;
      previous = item;
    }
    return line.replace(/\s+/g, " ").trim();
  }).filter(Boolean);
  const compact = (value: string) => value.replace(/\s/g, "");
  return compact(lines.join(" ")) === compact(target) ? lines : null;
}
