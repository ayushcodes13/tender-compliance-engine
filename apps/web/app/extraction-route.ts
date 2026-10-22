/** Prefer exact source-cell geometry when the tender has a recognized two-column technical table. */
export function shouldUseStructuredTableExtraction(input: {
  hasStructuredPages: boolean;
  hasVisualPages: boolean;
  hasModelCredentials: boolean;
}): boolean {
  return input.hasStructuredPages;
}
