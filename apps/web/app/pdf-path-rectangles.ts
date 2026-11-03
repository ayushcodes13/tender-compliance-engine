export type PdfPathOperations = {
  rectangle: number;
  moveTo: number;
  lineTo: number;
  closePath: number;
};

export type PdfRectangle = { x: number; y: number; width: number; height: number };

function distinctCoordinates(values: number[]): number[] {
  return values.sort((left, right) => left - right).filter((value, index, sorted) => index === 0 || Math.abs(value - sorted[index - 1]) > 2);
}

/** Recognizes a table-like grid from long, thin horizontal and vertical border paths. */
export function hasTableGridGeometry(rectangles: PdfRectangle[], pageWidth: number, pageHeight: number): boolean {
  const horizontal = distinctCoordinates(rectangles
    .filter((rectangle) => rectangle.width >= pageWidth * 0.2 && rectangle.height <= 2.5)
    .map((rectangle) => rectangle.y + rectangle.height / 2));
  const vertical = distinctCoordinates(rectangles
    .filter((rectangle) => rectangle.height >= pageHeight * 0.2 && rectangle.width <= 2.5)
    .map((rectangle) => rectangle.x + rectangle.width / 2));
  return horizontal.length >= 4 && vertical.length >= 4;
}

function rectangleFromPoints(points: Array<[number, number]>, minWidth: number, minHeight: number): PdfRectangle | null {
  if (points.length !== 4) return null;
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  const width = right - left;
  const height = bottom - top;
  if (width <= minWidth || height <= minHeight) return null;
  const corners = new Set(points.map(([x, y]) => `${Math.round(x * 100) / 100},${Math.round(y * 100) / 100}`));
  const expected = new Set([
    `${Math.round(left * 100) / 100},${Math.round(top * 100) / 100}`,
    `${Math.round(right * 100) / 100},${Math.round(top * 100) / 100}`,
    `${Math.round(right * 100) / 100},${Math.round(bottom * 100) / 100}`,
    `${Math.round(left * 100) / 100},${Math.round(bottom * 100) / 100}`,
  ]);
  return corners.size === 4 && [...expected].every((corner) => corners.has(corner))
    ? { x: left, y: top, width, height }
    : null;
}

/** Extracts large axis-aligned cell outlines from either PDF rectangle operators or closed four-corner paths. */
export function extractPdfPathRectangles(
  commands: number[],
  coordinates: number[],
  operations: PdfPathOperations,
  minWidth = 30,
  minHeight = 5,
): PdfRectangle[] {
  const rectangles: PdfRectangle[] = [];
  let commandIndex = 0;
  let coordinateIndex = 0;

  while (commandIndex < commands.length) {
    const command = commands[commandIndex];
    if (command === operations.rectangle) {
      const [x, y, width, height] = coordinates.slice(coordinateIndex, coordinateIndex + 4);
      coordinateIndex += 4;
      commandIndex += 1;
      if ([x, y, width, height].every(Number.isFinite) && Math.abs(width) > minWidth && Math.abs(height) > minHeight) {
        rectangles.push({ x: Math.min(x, x + width), y: Math.min(y, y + height), width: Math.abs(width), height: Math.abs(height) });
      }
      continue;
    }

    if (command !== operations.moveTo) break;
    const points: Array<[number, number]> = [[coordinates[coordinateIndex], coordinates[coordinateIndex + 1]]];
    coordinateIndex += 2;
    commandIndex += 1;
    while (commands[commandIndex] === operations.lineTo) {
      points.push([coordinates[coordinateIndex], coordinates[coordinateIndex + 1]]);
      coordinateIndex += 2;
      commandIndex += 1;
    }
    if (commands[commandIndex] !== operations.closePath) break;
    commandIndex += 1;
    const rectangle = rectangleFromPoints(points, minWidth, minHeight);
    if (rectangle) rectangles.push(rectangle);
  }

  return rectangles;
}
