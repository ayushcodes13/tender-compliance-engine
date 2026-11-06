export function hasRasterImageOperators(operatorCodes: number[], imageOperatorCodes: number[]): boolean {
  const imageOperators = new Set(imageOperatorCodes.filter(Number.isInteger));
  return operatorCodes.some((operatorCode) => imageOperators.has(operatorCode));
}

export function shouldRunPageOcr(input: {
  selectableText: string;
  textAreaRatio: number;
  hasRasterImageContent: boolean;
}): boolean {
  const text = input.selectableText.trim();
  if (text.length < 40) return true;
  // A short native header over a scanned table looks text-bearing to the router
  // but says little about the image region below it. OCR those sparse hybrid pages.
  return input.hasRasterImageContent
    && text.length <= 2_000
    && Number.isFinite(input.textAreaRatio)
    && input.textAreaRatio >= 0
    && input.textAreaRatio < 0.1;
}
