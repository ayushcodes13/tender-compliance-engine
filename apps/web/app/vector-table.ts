export type TableSourceItem = {
  str: string;
  x: number;
  y: number;
  box: { x: number; y: number; width: number; height: number } | null;
};

export type VectorRectangle = { x: number; y: number; width: number; height: number };

export type VectorTableRow = {
  quote: string;
  cells: string[];
  cellBoxes: Array<{ x: number; y: number; width: number; height: number } | null>;
  remark?: string;
  rowHeight: number;
  bbox: { x: number; y: number; width: number; height: number };
  remarkBox?: { x: number; y: number; width: number; height: number };
};

function uniqueRectangles(rectangles: VectorRectangle[], pageWidth: number, pageHeight: number): VectorRectangle[] {
  const body = rectangles.filter((cell) => cell.x > 2 && cell.y > 2
    && cell.width > 30 && cell.width < pageWidth * 0.95
    && cell.height > 5 && cell.height < pageHeight * 0.8);
  return body.filter((cell, index) => !body.slice(0, index).some((seen) =>
    Math.abs(seen.x - cell.x) < 0.25
      && Math.abs(seen.y - cell.y) < 0.25
      && Math.abs(seen.width - cell.width) < 0.25
      && Math.abs(seen.height - cell.height) < 0.25));
}

function cellContents(items: TableSourceItem[], cell: VectorRectangle) {
  const inside = items.filter((item) => item.x >= cell.x - 1
    && item.x <= cell.x + cell.width + 1
    && item.y >= cell.y - 1
    && item.y <= cell.y + cell.height + 2
    && item.str.trim());
  const boxes = inside.map((item) => item.box).filter((box): box is NonNullable<typeof box> => Boolean(box));
  const bbox = boxes.length ? {
    x: Math.min(...boxes.map((box) => box.x)),
    y: Math.min(...boxes.map((box) => box.y)),
    width: Math.max(...boxes.map((box) => box.x + box.width)) - Math.min(...boxes.map((box) => box.x)),
    height: Math.max(...boxes.map((box) => box.y + box.height)) - Math.min(...boxes.map((box) => box.y)),
  } : null;
  return { text: inside.map((item) => item.str).join(" ").replace(/\s+/g, " ").trim(), bbox };
}

function extractRowsFromGrid(
  items: TableSourceItem[],
  rectangles: VectorRectangle[],
  pageWidth: number,
  pageHeight: number,
): VectorTableRow[] {
  const rules = rectangles.filter((rectangle) => rectangle.width > pageWidth * 0.05
    && rectangle.height <= 2.5 && rectangle.height >= 0)
    .map((rectangle) => ({ y: rectangle.y + rectangle.height / 2, left: rectangle.x, right: rectangle.x + rectangle.width }))
    .filter((rule) => rule.left > 2 && rule.right < pageWidth - 2);
  const cellRectangles = uniqueRectangles(rectangles, pageWidth, pageHeight);
  const edgeFrequency = new Map<number, number>();
  for (const rectangle of cellRectangles) {
    for (const edge of [rectangle.x, rectangle.x + rectangle.width]) {
      if (edge < pageWidth * 0.04 || edge > pageWidth * 0.96) continue;
      const match = [...edgeFrequency.keys()].find((candidate) => Math.abs(candidate - edge) <= 8);
      const key = match ?? edge;
      edgeFrequency.set(key, (edgeFrequency.get(key) ?? 0) + 1);
    }
  }
  const cellEdges = [...edgeFrequency.keys()].sort((a, b) => a - b);
  const minCellEdge = cellEdges[0];
  const maxCellEdge = cellEdges[cellEdges.length - 1];
  const minimumEdgeFrequency = Math.max(5, Math.max(...edgeFrequency.values()) * 0.15);
  const frequentEntries = [...edgeFrequency.entries()]
    .filter(([, count]) => count >= minimumEdgeFrequency)
    .sort((a, b) => a[0] - b[0]);
  const ruleBands: Array<{ y: number; left: number; right: number; edges: number[] }> = [];
  for (const rule of rules.sort((a, b) => a.y - b.y)) {
    const band = ruleBands.find((candidate) => Math.abs(candidate.y - rule.y) <= 1.5);
    if (band) {
      band.left = Math.min(band.left, rule.left);
      band.right = Math.max(band.right, rule.right);
      band.edges.push(rule.left, rule.right);
    } else ruleBands.push({ ...rule, edges: [rule.left, rule.right] });
  }
  const tableRules = ruleBands.filter((band) => Math.abs(band.left - minCellEdge) <= 8
    && Math.abs(band.right - maxCellEdge) <= 8);
  const ruleEdgeFrequency = new Map<number, number>();
  for (const band of tableRules) {
    for (const edge of band.edges) {
      const match = [...ruleEdgeFrequency.keys()].find((candidate) => Math.abs(candidate - edge) <= 3);
      const key = match ?? edge;
      ruleEdgeFrequency.set(key, (ruleEdgeFrequency.get(key) ?? 0) + 1);
    }
  }
  const ruleColumnEdges = [...ruleEdgeFrequency.entries()]
    .filter(([, count]) => count >= 2)
    .map(([edge]) => edge)
    .sort((a, b) => a - b);
  const columnEdges = ruleColumnEdges.length >= 3
    ? ruleColumnEdges
    : frequentEntries.map(([edge]) => edge).sort((a, b) => a - b);
  const boundaries = tableRules.map((band) => band.y);
  if (boundaries.length < 3 || columnEdges.length < 3) return [];

  const output: VectorTableRow[] = [];
  for (let index = boundaries.length - 1; index > 0; index -= 1) {
    const lower = boundaries[index - 1];
    const upper = boundaries[index];
    if (upper - lower < 4) continue;
    const cellContentsForRow = columnEdges.slice(0, -1).map((left, columnIndex) => {
      const right = columnEdges[columnIndex + 1];
      const cellItems = items.filter((item) => item.x >= left - 1.5 && item.x < right - 0.5
        && item.y >= lower - 1.5 && item.y <= upper + 1.5 && item.str.trim())
        .sort((a, b) => b.y - a.y || a.x - b.x);
      const boxes = cellItems.map((item) => item.box).filter((box): box is NonNullable<typeof box> => Boolean(box));
      const bbox = boxes.length ? {
        x: Math.min(...boxes.map((box) => box.x)),
        y: Math.min(...boxes.map((box) => box.y)),
        width: Math.max(...boxes.map((box) => box.x + box.width)) - Math.min(...boxes.map((box) => box.x)),
        height: Math.max(...boxes.map((box) => box.y + box.height)) - Math.min(...boxes.map((box) => box.y)),
      } : null;
      return { text: cellItems.map((item) => item.str).join(" ").replace(/\s+/g, " ").trim(), bbox };
    });
    if (!cellContentsForRow.some((cell) => cell.text)) continue;
    const first = cellContentsForRow.find((cell) => cell.text && cell.bbox);
    if (!first?.bbox) continue;
    const populatedRight = cellContentsForRow.slice(1).filter((cell) => cell.text && cell.bbox);
    const remarkBox = populatedRight.length ? {
      x: Math.min(...populatedRight.map((cell) => cell.bbox!.x)),
      y: Math.min(...populatedRight.map((cell) => cell.bbox!.y)),
      width: Math.max(...populatedRight.map((cell) => cell.bbox!.x + cell.bbox!.width)) - Math.min(...populatedRight.map((cell) => cell.bbox!.x)),
      height: Math.max(...populatedRight.map((cell) => cell.bbox!.y + cell.bbox!.height)) - Math.min(...populatedRight.map((cell) => cell.bbox!.y)),
    } : undefined;
    output.push({
      quote: first.text,
      cells: cellContentsForRow.map((cell) => cell.text),
      cellBoxes: cellContentsForRow.map((cell) => cell.bbox),
      ...(populatedRight.length ? { remark: populatedRight.map((cell) => cell.text).join(" ") } : {}),
      rowHeight: upper - lower,
      bbox: first.bbox,
      ...(remarkBox ? { remarkBox } : {}),
    });
  }
  return output;
}

/** Uses vector cell boundaries only to associate selectable source text with table rows and columns. */
export function extractVectorTableRows(
  items: TableSourceItem[],
  rectangles: VectorRectangle[],
  pageWidth: number,
  pageHeight: number,
): VectorTableRow[] {
  const gridRows = extractRowsFromGrid(items, rectangles, pageWidth, pageHeight);
  if (gridRows.length > 0) return gridRows;
  const cells = uniqueRectangles(rectangles, pageWidth, pageHeight)
    .filter((cell) => cell.width > 8 && cell.height > 5);
  const rowBands: Array<{ top: number; cells: VectorRectangle[] }> = [];
  for (const cell of cells) {
    const top = cell.y + cell.height;
    let band = rowBands.find((candidate) => Math.abs(candidate.top - top) <= 1.5);
    if (!band) {
      band = { top, cells: [] };
      rowBands.push(band);
    }
    band.cells.push(cell);
  }
  const consolidatedBands = rowBands.map((band) => {
    const outerCells = band.cells.filter((cell) => !band.cells.some((outer) => outer !== cell
      && outer.width > cell.width + 8
      && outer.height >= cell.height
      && outer.x <= cell.x + 1.5
      && outer.x + outer.width >= cell.x + cell.width - 1.5
      && outer.y <= cell.y + 1.5
      && outer.y + outer.height >= cell.y + cell.height - 1.5));
    const columns: VectorRectangle[] = [];
    for (const cell of outerCells) {
      const existingIndex = columns.findIndex((candidate) => Math.abs(candidate.x - cell.x) <= 1.5
        && Math.abs(candidate.width - cell.width) <= 5);
      if (existingIndex < 0) columns.push(cell);
      else if (cell.height > columns[existingIndex].height) columns[existingIndex] = cell;
    }
    return { ...band, cells: columns.sort((a, b) => a.x - b.x) };
  });
  const allBandCells = rowBands.flatMap((band) => band.cells);
  const rows = consolidatedBands
    .filter((band) => band.cells.length >= 2)
    .filter((band) => !band.cells.every((cell) => allBandCells.some((outer) => outer !== cell
      && outer.width > cell.width + 8
      && outer.x <= cell.x + 1.5
      && outer.x + outer.width >= cell.x + cell.width - 1.5
      && outer.height > cell.height + 1
      && outer.y <= cell.y + 1
      && outer.y + outer.height >= cell.y + cell.height - 1)))
    .sort((a, b) => b.top - a.top || a.cells[0].x - b.cells[0].x);
  const output: VectorTableRow[] = [];

  for (const band of rows) {
    const rowCells = band.cells.sort((a, b) => a.x - b.x);
    const cellContentsForRow = rowCells.map((cell) => cellContents(items, cell));
    const cells = cellContentsForRow.map((content) => content.text);
    const firstContent = cellContentsForRow.find((content) => content.text && content.bbox);
    if (!firstContent?.bbox) continue;
    const rightContents = cellContentsForRow.slice(1).filter((content) => content.text && content.bbox);
    const remark = rightContents.map((content) => content.text).join(" ").replace(/\s+/g, " ").trim();
    const remarkBoxes = rightContents.map((content) => content.bbox!).filter(Boolean);
    const remarkBox = remarkBoxes.length ? {
      x: Math.min(...remarkBoxes.map((box) => box.x)),
      y: Math.min(...remarkBoxes.map((box) => box.y)),
      width: Math.max(...remarkBoxes.map((box) => box.x + box.width)) - Math.min(...remarkBoxes.map((box) => box.x)),
      height: Math.max(...remarkBoxes.map((box) => box.y + box.height)) - Math.min(...remarkBoxes.map((box) => box.y)),
    } : undefined;
    output.push({
      quote: firstContent.text,
      cells,
      cellBoxes: cellContentsForRow.map((content) => content.bbox),
      ...(remark ? { remark } : {}),
      rowHeight: Math.max(...rowCells.map((cell) => cell.height)),
      bbox: firstContent.bbox,
      ...(remarkBox ? { remarkBox } : {}),
    });
  }

  return output;
}

/** Excludes a repeated table header by comparing every populated source cell with the detected header map. */
export function isRepeatedTableHeader(cells: string[], headers: string[]): boolean {
  const normalize = (value: string) => /^(?:s(?:r|l)?\.?\s*no\.?|serial\s+no\.?)$/i.test(value.trim()) ? "serial-no" : value.replace(/\s+/g, " ").trim();
  const known = new Set([...headers, "s.no.", "s.no", "sr.no.", "sr.no", "sr no", "serial no", "sl.no", "sl no"].map(normalize).filter(Boolean));
  const populated = cells.map(normalize).filter(Boolean);
  if (!populated.length) return false;
  const matched = populated.filter((cell) => known.has(cell)).length;
  return matched >= 2 && matched / populated.length >= 0.75
    || (populated.length === 1 && known.has(populated[0]) && !/^\d+$/.test(populated[0]));
}
