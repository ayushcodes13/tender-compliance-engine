export type VisualOcrConfidence = "high" | "medium" | "low";

/** Accept a visual row transcription only when it preserves every selectable source token in order. */
export function validateVisualRowTranscription(
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
