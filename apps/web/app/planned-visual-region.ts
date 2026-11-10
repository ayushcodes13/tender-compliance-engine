import type { SourceBox } from "./source-document";

export type PixelRect = { left: number; top: number; right: number; bottom: number };

/** Maps an approximate PDF.js image box into a padded, clamped rendered-image crop. */
export function imageRegionCropRect(input: {
  bbox: SourceBox;
  pageSize: { width: number; height: number };
  imageSize: { width: number; height: number };
  paddingRatio?: number;
}): PixelRect | null {
  const { bbox, pageSize, imageSize } = input;
  const numbers = [bbox.x, bbox.y, bbox.width, bbox.height, pageSize.width, pageSize.height, imageSize.width, imageSize.height,
    ...(input.paddingRatio === undefined ? [] : [input.paddingRatio])];
  if (numbers.some((value) => !Number.isFinite(value)) || bbox.width <= 0 || bbox.height <= 0
    || pageSize.width <= 0 || pageSize.height <= 0 || imageSize.width <= 0 || imageSize.height <= 0
    || (input.paddingRatio ?? 0.035) < 0 || (input.paddingRatio ?? 0.035) > 0.25) return null;

  const scaleX = imageSize.width / pageSize.width;
  const scaleY = imageSize.height / pageSize.height;
  const paddingRatio = input.paddingRatio ?? 0.035;
  const paddingX = Math.max(2, bbox.width * scaleX * paddingRatio);
  const paddingY = Math.max(2, bbox.height * scaleY * paddingRatio);
  const left = Math.max(0, Math.floor(bbox.x * scaleX - paddingX));
  const top = Math.max(0, Math.floor(bbox.y * scaleY - paddingY));
  const right = Math.min(imageSize.width, Math.ceil((bbox.x + bbox.width) * scaleX + paddingX));
  const bottom = Math.min(imageSize.height, Math.ceil((bbox.y + bbox.height) * scaleY + paddingY));
  if (right <= left || bottom <= top) return null;
  return { left, top, right, bottom };
}
