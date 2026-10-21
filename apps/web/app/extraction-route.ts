/** Keep structured geometry extraction as the no-vision fallback. */
export function shouldUseStructuredTableExtraction(input: {
  hasStructuredPages: boolean;
  hasVisualPages: boolean;
  hasModelCredentials: boolean;
}): boolean {
  return input.hasStructuredPages && (!input.hasVisualPages || !input.hasModelCredentials);
}
