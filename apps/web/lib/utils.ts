import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge and deduplicate Tailwind class names.
 *
 * The standard shadcn/ui helper: combines `clsx` for arbitrary/composable
 * class handling with `tailwind-merge` so later classes in conditional
 * expressions override earlier ones instead of stacking.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
