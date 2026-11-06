import { imageRegionNativeTextCoverage, MIN_IMAGE_REGION_AREA_RATIO_FOR_OCR } from "./pdf-image-regions.ts";

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
  const hasImageRegionWithSparseNativeText = input.imageRegions?.some((region) => region.areaRatio >= MIN_IMAGE_REGION_AREA_RATIO_FOR_OCR
    && imageRegionNativeTextCoverage(region.bbox, input.nativeTextBoxes ?? []) < 0.25) ?? false;
  if (input.hasRasterImageContent && hasImageRegionWithSparseNativeText) return true;
  // A short native header over a scanned table looks text-bearing to the router
  // but says little about the image region below it. OCR those sparse hybrid pages.
  return input.hasRasterImageContent
    && text.length <= 2_000
    && Number.isFinite(input.textAreaRatio)
    && input.textAreaRatio >= 0
    && input.textAreaRatio < 0.1;
}
