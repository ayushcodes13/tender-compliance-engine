export type SourceBox = { x: number; y: number; width: number; height: number };

export type SourceTextItem = {
  str: string;
  x: number;
  y: number;
  box: SourceBox | null;
  fontName?: string;
  bold?: boolean;
};

export type PdfRectangle = { x: number; y: number; width: number; height: number };

export type StructuredRequirement = {
  parameter: string;
  specifications: string[];
  quote: string;
  bbox: SourceBox;
};

export type StructuredSection = {
  sectionTitle: string;
  sectionHeading: string;
  requirements: StructuredRequirement[];
};

type TextLine = { y: number; items: SourceTextItem[]; text: string };
type Cell = { x: number; y: number; width: number; height: number };

function normalize(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function textLines(items: SourceTextItem[]): TextLine[] {
  const sorted = items.filter((item) => item.str.trim()).sort((a, b) => b.y - a.y || a.x - b.x);
  const lines: TextLine[] = [];

  for (const item of sorted) {
    const line = lines.find((candidate) => Math.abs(candidate.y - item.y) <= 2.5);
    if (line) {
      line.items.push(item);
      line.items.sort((a, b) => a.x - b.x);
      line.text = normalize(line.items.map((entry) => entry.str).join(" "));
    } else {
      lines.push({ y: item.y, items: [item], text: normalize(item.str) });
    }
  }
  return lines.sort((a, b) => b.y - a.y);
}

function sameBand(left: Cell, right: Cell): boolean {
  return Math.abs(left.x - right.x) <= 1
    && Math.abs(left.width - right.width) <= 1
    && Math.abs(left.y - right.y) <= 1
    && Math.abs(left.height - right.height) <= 1;
}

function sameRow(left: Cell, right: Cell): boolean {
  return Math.abs(left.y - right.y) <= 1 && Math.abs(left.height - right.height) <= 1;
}

function cellAtText(rectangles: PdfRectangle[], item: SourceTextItem): Cell | null {
  return rectangles
    .filter((cell) => item.x >= cell.x - 1
      && item.x <= cell.x + cell.width + 1
      && item.y >= cell.y - 1
      && item.y <= cell.y + cell.height + 2)
    .sort((left, right) => left.width * left.height - right.width * right.height)[0] ?? null;
}

function insideCell(item: SourceTextItem, cell: Cell): boolean {
  return item.x >= cell.x - 1
    && item.x <= cell.x + cell.width + 1
    && item.y >= cell.y - 1
    && item.y <= cell.y + cell.height + 2;
}

function cellItems(items: SourceTextItem[], cell: Cell): SourceTextItem[] {
  return items.filter((item) => insideCell(item, cell));
}

function bounds(items: SourceTextItem[]): SourceBox | null {
  const boxes = items.map((item) => item.box).filter((box): box is SourceBox => Boolean(box));
  if (!boxes.length) return null;
  const left = Math.min(...boxes.map((box) => box.x));
  const top = Math.min(...boxes.map((box) => box.y));
  const right = Math.max(...boxes.map((box) => box.x + box.width));
  const bottom = Math.max(...boxes.map((box) => box.y + box.height));
  return { x: left, y: top, width: right - left, height: bottom - top };
}

function cellText(items: SourceTextItem[]): { quote: string; specifications: string[]; bbox: SourceBox | null } {
  const lines = textLines(items);
  const quote = normalize(lines.map((line) => line.text).join(" "));
  const specifications: string[] = [];
  let current = "";

  for (const line of lines) {
    const text = normalize(line.text);
    if (!text) continue;
    if (text.startsWith("•")) {
      if (current) specifications.push(current);
      current = normalize(text.slice(1));
    } else if (current) {
      current = normalize(`${current} ${text}`);
    } else {
      current = text;
    }
  }
  if (current) specifications.push(current);

  return { quote, specifications, bbox: bounds(items) };
}

function bulletSection(items: SourceTextItem[], heading: SourceTextItem, lines: TextLine[], contentFloor: number): StructuredRequirement | null {
  const headingY = heading.y;
  const markers = items.filter((item) => {
    const text = item.str.trim();
    return (text === "•" || text.startsWith("•"))
      && item.x >= heading.x - 25
      && item.y < headingY - 4
      && item.y > contentFloor;
  }).sort((a, b) => b.y - a.y);

  if (!markers.length) return null;
  const specs: string[] = [];
  const quoteParts: string[] = [];
  const sourceItems: SourceTextItem[] = [];

  markers.forEach((marker, index) => {
    const nextY = markers[index + 1]?.y ?? contentFloor;
    const lineItems = lines
      .filter((line) => line.y <= marker.y + 1 && line.y > nextY + 1)
      .flatMap((line) => line.items)
      .filter((item) => item.x >= heading.x - 2 && item.y < headingY - 2);
    const content = normalize(lineItems
      .filter((item) => item !== marker)
      .map((item) => item.str.replace(/^•\s*/, ""))
      .join(" "));
    if (!content) return;
    specs.push(content);
    quoteParts.push(`• ${content}`);
    sourceItems.push(marker, ...lineItems);
  });

  const bbox = bounds([heading, ...sourceItems]);
  if (!specs.length || !bbox) return null;
  return { parameter: "Other requirements", specifications: specs, quote: quoteParts.join(" "), bbox };
}

/**
 * Recover two-column technical requirement tables from their visible PDF cell
 * rectangles. The text remains sourced from the selectable text layer; the
 * vector geometry is only used to associate each parameter with its cell.
 */
export function extractStructuredTechnicalSection(
  items: SourceTextItem[],
  rectangles: PdfRectangle[],
  pageHeight = 842,
): StructuredSection | null {
  const lines = textLines(items);
  const headerLine = lines.find((line) => /\bParameter\b/i.test(line.text) && /\bRequired Specification\b/i.test(line.text));
  const sectionHeadingLine = lines.find((line) => /Technical requirements of/i.test(line.text));
  if (!headerLine || !sectionHeadingLine) return null;

  const parameterHeader = headerLine.items.find((item) => /\bParameter\b/i.test(item.str));
  const specificationHeader = headerLine.items.find((item) => /\bRequired Specification\b/i.test(item.str));
  if (!parameterHeader || !specificationHeader) return null;

  const leftHeaderCell = cellAtText(rectangles, parameterHeader);
  const rightHeaderCell = cellAtText(rectangles, specificationHeader);
  if (!leftHeaderCell || !rightHeaderCell) return null;

  const bodyRows = rectangles.filter((cell) => cell.y + cell.height < leftHeaderCell.y + leftHeaderCell.height - 1);
  const leftCells = bodyRows.filter((cell) => sameBand({ ...cell, y: 0, height: 0 }, { ...leftHeaderCell, y: 0, height: 0 }));
  const rightCells = bodyRows.filter((cell) => sameBand({ ...cell, y: 0, height: 0 }, { ...rightHeaderCell, y: 0, height: 0 }));
  const rows: Array<{ left: Cell; right: Cell }> = [];

  for (const left of leftCells) {
    const right = rightCells.find((candidate) => sameRow(left, candidate));
    if (right) rows.push({ left, right });
  }
  rows.sort((a, b) => b.left.y + b.left.height - (a.left.y + a.left.height));
  if (rows.length < 2) return null;

  const requirements: StructuredRequirement[] = [];
  for (const row of rows) {
    const parameterItems = cellItems(items, row.left);
    const specificationItems = cellItems(items, row.right);
    const parameter = normalize(textLines(parameterItems).map((line) => line.text).join(" "));
    if (!parameter || /^(parameter)$/i.test(parameter)) continue;
    const specification = cellText(specificationItems);
    const parameterBox = bounds(parameterItems);
    const quote = specification.quote || parameter;
    const bbox = bounds([...parameterItems, ...specificationItems]) ?? specification.bbox ?? parameterBox;
    if (!bbox) continue;
    requirements.push({
      parameter,
      specifications: specification.specifications,
      quote,
      bbox,
    });
  }

  const sectionTitle = lines.find((line) => /^Section\s+\d+\s*[–-]/i.test(line.text))?.text ?? "Technical specifications";
  const sectionHeading = sectionHeadingLine.text.replace(/^[▪●•\uF0A7]\s*/u, "");
  const otherHeading = items.find((item) => /^Other requirements:?$/i.test(normalize(item.str)));
  const other = otherHeading ? bulletSection(items, otherHeading, lines, Math.max(40, pageHeight * 0.11)) : null;
  if (other) requirements.push(other);
  if (!requirements.length) return null;

  return { sectionTitle, sectionHeading, requirements };
}
