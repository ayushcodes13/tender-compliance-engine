import type { SourceBox } from "./source-document.ts";

export type PdfImageOperatorCodes = {
  save: number;
  restore: number;
  transform: number;
  paintFormXObjectBegin: number;
  paintFormXObjectEnd: number;
  image: number[];
  imageGroup: number[];
  imageRepeat: number[];
  imageMaskRepeat: number[];
};

type Matrix = [number, number, number, number, number, number];

export type PdfImageRegion = {
  bbox: SourceBox;
  areaRatio: number;
  operator: "image" | "image-group" | "image-repeat";
};

// Repeated logos/icons are common in native-text tenders; keep them visible
// for review without causing a whole-page OCR pass by themselves.
export const MIN_IMAGE_REGION_AREA_RATIO_FOR_OCR = 0.05;

const IDENTITY: Matrix = [1, 0, 0, 1, 0, 0];

function multiply(left: Matrix, right: Matrix): Matrix {
  return [
    left[0] * right[0] + left[2] * right[1],
    left[1] * right[0] + left[3] * right[1],
    left[0] * right[2] + left[2] * right[3],
    left[1] * right[2] + left[3] * right[3],
    left[0] * right[4] + left[2] * right[5] + left[4],
    left[1] * right[4] + left[3] * right[5] + left[5],
  ];
}

function asMatrix(value: unknown): Matrix | null {
  if (!Array.isArray(value) || value.length !== 6 || !value.every((part) => typeof part === "number" && Number.isFinite(part))) return null;
  return value as Matrix;
}

function transformedBox(matrix: Matrix, viewportTransform: Matrix, pageSize: { width: number; height: number }): SourceBox | null {
  const transform = multiply(viewportTransform, matrix);
  const points = [[0, 0], [1, 0], [0, 1], [1, 1]].map(([x, y]) => ({
    x: x * transform[0] + y * transform[2] + transform[4],
    y: x * transform[1] + y * transform[3] + transform[5],
  }));
  const x = Math.max(0, Math.min(...points.map((point) => point.x)));
  const y = Math.max(0, Math.min(...points.map((point) => point.y)));
  const right = Math.min(pageSize.width, Math.max(...points.map((point) => point.x)));
  const bottom = Math.min(pageSize.height, Math.max(...points.map((point) => point.y)));
  if (![x, y, right, bottom].every(Number.isFinite) || right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}

export function collectPdfImageRegions(input: {
  fnArray: number[];
  argsArray: unknown[];
  codes: PdfImageOperatorCodes;
  viewportTransform: number[];
  pageSize: { width: number; height: number };
}): PdfImageRegion[] {
  const viewportTransform = asMatrix(input.viewportTransform);
  if (!viewportTransform) return [];
  const imageCodes = new Set(input.codes.image);
  const groupCodes = new Set(input.codes.imageGroup);
  const repeatCodes = new Set(input.codes.imageRepeat);
  const maskRepeatCodes = new Set(input.codes.imageMaskRepeat);
  let matrix: Matrix = [...IDENTITY];
  const stack: Matrix[] = [];
  const regions: PdfImageRegion[] = [];
  const pageArea = input.pageSize.width * input.pageSize.height;

  const addRegion = (current: Matrix, operator: PdfImageRegion["operator"]) => {
    const bbox = transformedBox(current, viewportTransform, input.pageSize);
    if (!bbox) return;
    const areaRatio = pageArea > 0 ? Math.min(1, (bbox.width * bbox.height) / pageArea) : 0;
    regions.push({ bbox, areaRatio, operator });
  };

  for (let index = 0; index < input.fnArray.length; index += 1) {
    const code = input.fnArray[index];
    const args = input.argsArray[index];
    if (code === input.codes.save || code === input.codes.paintFormXObjectBegin) {
      stack.push([...matrix]);
      if (code === input.codes.paintFormXObjectBegin && Array.isArray(args)) {
        const formMatrix = asMatrix(args[0]);
        if (formMatrix) matrix = multiply(matrix, formMatrix);
      }
      continue;
    }
    if (code === input.codes.restore || code === input.codes.paintFormXObjectEnd) {
      matrix = stack.pop() ?? [...IDENTITY];
      continue;
    }
    if (code === input.codes.transform && Array.isArray(args)) {
      const next = asMatrix(args);
      if (next) matrix = multiply(matrix, next);
      continue;
    }
    if (imageCodes.has(code)) {
      addRegion(matrix, "image");
      continue;
    }
    if (groupCodes.has(code) && Array.isArray(args)) {
      const entries = Array.isArray(args[1]) ? args[1] : args[0];
      if (Array.isArray(entries)) {
        for (const entry of entries) {
          if (!entry || typeof entry !== "object") continue;
          const imageTransform = asMatrix((entry as { transform?: unknown }).transform);
          if (imageTransform) addRegion(multiply(matrix, imageTransform), "image-group");
        }
      }
      continue;
    }
    if (repeatCodes.has(code) && Array.isArray(args)) {
      const scaleX = args[1];
      const scaleY = args[2];
      const positions = args[3];
      if (typeof scaleX === "number" && Number.isFinite(scaleX)
        && typeof scaleY === "number" && Number.isFinite(scaleY)
        && Array.isArray(positions)) {
        for (let position = 0; position + 1 < positions.length; position += 2) {
          const x = positions[position];
          const y = positions[position + 1];
          if (typeof x !== "number" || !Number.isFinite(x) || typeof y !== "number" || !Number.isFinite(y)) continue;
          addRegion(multiply(matrix, [scaleX, 0, 0, scaleY, x, y]), "image-repeat");
        }
      }
      continue;
    }
    if (maskRepeatCodes.has(code) && Array.isArray(args)) {
      const [a, b, c, d] = args.slice(1, 5);
      const positions = args[5];
      if ([a, b, c, d].every((part) => typeof part === "number" && Number.isFinite(part)) && Array.isArray(positions)) {
        for (let position = 0; position + 1 < positions.length; position += 2) {
          const x = positions[position];
          const y = positions[position + 1];
          if (typeof x !== "number" || !Number.isFinite(x) || typeof y !== "number" || !Number.isFinite(y)) continue;
          addRegion(multiply(matrix, [a as number, b as number, c as number, d as number, x, y]), "image-repeat");
        }
      }
    }
  }
  return regions;
}

export function imageRegionNativeTextCoverage(region: SourceBox, textBoxes: SourceBox[]): number {
  const area = region.width * region.height;
  if (area <= 0) return 0;
  const overlap = textBoxes.reduce((total, box) => {
    const width = Math.max(0, Math.min(region.x + region.width, box.x + box.width) - Math.max(region.x, box.x));
    const height = Math.max(0, Math.min(region.y + region.height, box.y + box.height) - Math.max(region.y, box.y));
    return total + width * height;
  }, 0);
  return Math.min(1, overlap / area);
}
