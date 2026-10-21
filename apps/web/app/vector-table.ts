export type TableSourceItem = {
  str: string;
  x: number;
  y: number;
  box: { x: number; y: number; width: number; height: number } | null;
};

export type VectorRectangle = { x: number; y: number; width: number; height: number };

export type VectorTableRow = {
  quote: string;
  remark?: string;
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

function clusterLeftCells(cells: VectorRectangle[]): VectorRectangle[][] {
  const clusters: VectorRectangle[][] = [];
  for (const cell of cells.sort((a, b) => a.x - b.x || a.width - b.width)) {
    let cluster = clusters.find((entries) => Math.abs(entries[0].x - cell.x) <= 3
      && Math.abs(entries[0].width - cell.width) <= 5);
    if (!cluster) {
      cluster = [];
      clusters.push(cluster);
    }
    cluster.push(cell);
  }
  return clusters.filter((cluster) => cluster.length >= 2);
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

/** Uses vector cell boundaries only to associate selectable source text with table rows and columns. */
export function extractVectorTableRows(
  items: TableSourceItem[],
  rectangles: VectorRectangle[],
  pageWidth: number,
  pageHeight: number,
): VectorTableRow[] {
  const leftCellClusters = clusterLeftCells(uniqueRectangles(rectangles, pageWidth, pageHeight)
    .filter((cell) => cell.width > pageWidth * 0.35 && cell.width < pageWidth * 0.8));
  const leftCells = leftCellClusters.flat();
  const rows = leftCells.sort((a, b) => b.y + b.height - (a.y + a.height) || a.x - b.x);
  const output: VectorTableRow[] = [];

  for (const left of rows) {
    const leftContent = cellContents(items, left);
    if (!leftContent.text || !leftContent.bbox) continue;
    const right = uniqueRectangles(rectangles, pageWidth, pageHeight)
      .filter((cell) => cell.x >= left.x + left.width - 2
        && Math.abs(cell.y - left.y) <= 1
        && Math.abs(cell.height - left.height) <= 1)
      .sort((a, b) => a.x - b.x);
    const rightContents = right.map((cell) => cellContents(items, cell)).filter((content) => content.text && content.bbox);
    const remark = rightContents.map((content) => content.text).join(" ").replace(/\s+/g, " ").trim();
    const remarkBoxes = rightContents.map((content) => content.bbox!).filter(Boolean);
    const remarkBox = remarkBoxes.length ? {
      x: Math.min(...remarkBoxes.map((box) => box.x)),
      y: Math.min(...remarkBoxes.map((box) => box.y)),
      width: Math.max(...remarkBoxes.map((box) => box.x + box.width)) - Math.min(...remarkBoxes.map((box) => box.x)),
      height: Math.max(...remarkBoxes.map((box) => box.y + box.height)) - Math.min(...remarkBoxes.map((box) => box.y)),
    } : undefined;
    output.push({ quote: leftContent.text, ...(remark ? { remark } : {}), bbox: leftContent.bbox, ...(remarkBox ? { remarkBox } : {}) });
  }

  return output;
}
