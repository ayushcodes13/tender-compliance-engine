/** Keep deterministic source-cell extraction as the offline fallback; configured models must route pages first. */
export function shouldUseStructuredTableExtraction(input: {
  hasStructuredPages: boolean;
  hasVisualPages: boolean;
  hasModelCredentials: boolean;
}): boolean {
  return input.hasStructuredPages && !input.hasModelCredentials;
}

/** Every text-bearing page is eligible for LLM section routing, including borderless schedules. */
export function technicalRoutingPages<T extends { page: number; text: string }>(pages: T[]): T[] {
  return pages.filter((page) => page.text.trim().length > 0);
}
