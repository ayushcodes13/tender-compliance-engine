export type VisualOcrConfidence = "high" | "medium" | "low";

/** Retain a model completion as a proposal only when it preserves selectable source tokens. */
export function validateVisualCompletionProposal(
  selectableQuote: string,
  visualQuote: string,
  confidence: VisualOcrConfidence,
): string | null {
  const source = selectableQuote.trim();
  const transcription = visualQuote.trim();
  if (confidence !== "high" || !source || !transcription || transcription.length > 5_000) return null;

  // Operators, signs, decimal separators and unit case carry technical meaning.
  const tokens = (value: string) => value.match(/>=|<=|!=|[<>≤≥±=−–-]|\d+(?:[.,]\d+)*|[\p{L}\p{N}]+|[°%µμ]/gu) ?? [];
  const sourceTokens = tokens(source);
  const visualTokens = tokens(transcription);
  if (!sourceTokens.length || visualTokens.length <= sourceTokens.length) return null;

  let visualIndex = 0;
  for (const token of sourceTokens) {
    while (visualIndex < visualTokens.length && visualTokens[visualIndex] !== token) visualIndex += 1;
    if (visualIndex >= visualTokens.length) return null;
    visualIndex += 1;
  }
  return transcription;
}

export function separateVisualCompletionProposal(
  selectableQuote: string,
  visualQuote: string,
  confidence: VisualOcrConfidence,
): { sourceQuote: string; unverifiedSuggestion?: string } {
  const sourceQuote = selectableQuote.trim();
  const suggestion = validateVisualCompletionProposal(sourceQuote, visualQuote, confidence);
  return { sourceQuote, ...(suggestion ? { unverifiedSuggestion: suggestion } : {}) };
}
