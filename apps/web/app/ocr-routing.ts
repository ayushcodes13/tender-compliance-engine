import { imageRegionNativeTextCoverage, MIN_IMAGE_REGION_AREA_RATIO_FOR_OCR } from "./pdf-image-regions.ts";

/** Regions large enough to matter and not already covered by selectable text. */
export function selectImageRegionsForOcr<T extends { bbox: { x: number; y: number; width: number; height: number }; areaRatio: number }>(regions: T[], nativeTextBoxes: Array<{ x: number; y: number; width: number; height: number }>): Array<T & { index: number }> {
  return regions.flatMap((region, index) => region.areaRatio >= MIN_IMAGE_REGION_AREA_RATIO_FOR_OCR
    && imageRegionNativeTextCoverage(region.bbox, nativeTextBoxes) < 0.25
    ? [{ ...region, index }]
    : []);
}

export function hasRasterImageOperators(operatorCodes: number[], imageOperatorCodes: number[]): boolean {
  const imageOperators = new Set(imageOperatorCodes.filter(Number.isInteger));
  return operatorCodes.some((operatorCode) => imageOperators.has(operatorCode));
}

export function shouldRunPageOcr(input: {
  selectableText: string;
  textAreaRatio: number;
  hasRasterImageContent: boolean;
  imageRegions?: Array<{ bbox: { x: number; y: number; width: number; height: number }; areaRatio: number }>;
  nativeTextBoxes?: Array<{ x: number; y: number; width: number; height: number }>;
}): boolean {
  const text = input.selectableText.trim();
  if (text.length < 40) return true;
  const hasImageRegionWithSparseNativeText = input.imageRegions
    ? selectImageRegionsForOcr(input.imageRegions, input.nativeTextBoxes ?? []).length > 0
    : false;
  if (input.hasRasterImageContent && hasImageRegionWithSparseNativeText) return true;
  // A short native header over a scanned table looks text-bearing to the router
  // but says little about the image region below it. OCR those sparse hybrid pages.
  return input.hasRasterImageContent
    && text.length <= 2_000
    && Number.isFinite(input.textAreaRatio)
    && input.textAreaRatio >= 0
    && input.textAreaRatio < 0.1;
}
