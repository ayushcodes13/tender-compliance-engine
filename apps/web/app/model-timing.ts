export type ModelTimingEvent = {
  phase: "headers_received" | "response_parsed";
  requestKind: "general_requirement_extraction";
  batchPageCount: number;
  inputCharacters: number;
  requestHeadersWaitMs?: number;
  responseBodyAndEnvelopeMs?: number;
  jsonParseMs?: number;
  responseStatus: number;
  responseCharacters?: number;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
};

const SAFE_NUMERIC_FIELDS = [
  "batchPageCount",
  "inputCharacters",
  "requestHeadersWaitMs",
  "responseBodyAndEnvelopeMs",
  "jsonParseMs",
  "responseStatus",
  "responseCharacters",
  "promptTokens",
  "completionTokens",
  "totalTokens",
] as const;

/**
 * Opt-in operational timing. The whitelist intentionally excludes prompts,
 * tender text, filenames, model output, credentials, and document identifiers.
 */
export function emitModelTiming(
  event: ModelTimingEvent,
  logger: (message: string) => void = (message) => console.info(message),
  enabled = process.env.TCE_MODEL_TIMING === "1",
): void {
  if (!enabled) return;
  const safe: Record<string, string | number> = {
    phase: event.phase,
    requestKind: event.requestKind,
  };
  for (const field of SAFE_NUMERIC_FIELDS) {
    const value = event[field];
    if (typeof value === "number" && Number.isFinite(value)) safe[field] = value;
  }
  logger(`[TCE_MODEL_TIMING] ${JSON.stringify(safe)}`);
}
