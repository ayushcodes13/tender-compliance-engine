export type PdfCacheKeyInput = {
  name: string;
  size: number;
  lastModified?: number;
};

export type BoundingBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const documentCache = new Map<string, { promise: Promise<any>; timestamp: number }>();

export function getPdfDocumentCacheKey(input: PdfCacheKeyInput): string {
  return `${input.name}:${input.size}:${input.lastModified ?? 0}`;
}

export function getCachedPdfDocument(key: string): Promise<any> | undefined {
  const entry = documentCache.get(key);
  return entry?.promise;
}

export function setCachedPdfDocument(key: string, promise: Promise<any>): void {
  documentCache.set(key, { promise, timestamp: Date.now() });
}

export function clearPdfDocumentCache(): void {
  documentCache.clear();
}

export function calculateTargetScrollTop(
  pageOffsetTop: number,
  pageHeight: number,
  box: BoundingBox | null | undefined,
  stageHeight: number
): number {
  if (!box) {
    // Scroll so top of the page is comfortably positioned in the stage
    return Math.max(0, pageOffsetTop - 24);
  }
  // If box has y percentage, calculate exact pixel position
  const boxTopInPage = (box.y / 100) * pageHeight;
  const targetTop = pageOffsetTop + boxTopInPage;
  return Math.max(0, targetTop - stageHeight * 0.38);
}

export function getVisiblePageFromOffsets(
  pageTops: Array<{ pageNumber: number; top: number; bottom: number }>,
  currentScrollTop: number,
  stageHeight: number
): number {
  if (pageTops.length === 0) return 1;
  const viewCenter = currentScrollTop + stageHeight * 0.4;
  for (const item of pageTops) {
    if (viewCenter >= item.top && viewCenter <= item.bottom) {
      return item.pageNumber;
    }
  }
  // Fallback: closest page
  let closest = pageTops[0];
  let minDiff = Math.abs(currentScrollTop - closest.top);
  for (let i = 1; i < pageTops.length; i++) {
    const diff = Math.abs(currentScrollTop - pageTops[i].top);
    if (diff < minDiff) {
      minDiff = diff;
      closest = pageTops[i];
    }
  }
  return closest.pageNumber;
}
