export type ModelTimingEvent = {
  phase: "request_started" | "headers_received" | "response_parsed" | "request_failed";
  requestKind: "page_routing" | "general_requirement_extraction" | "text_page_omission_audit" | "vector_table_column_mapping" | "vector_table_row_classification" | "vector_source_row_audit";
  failureKind?: "provider_busy" | "provider_connection" | "provider_timeout" | "request_aborted" | "other";
  batchIndex?: number;
  totalBatches?: number;
  pageNumbers?: number[];
  pageNumber?: number;
  batchPageCount: number;
  inputCharacters: number;
  requestHeadersWaitMs?: number;
  requestElapsedMs?: number;
  responseBodyAndEnvelopeMs?: number;
  jsonParseMs?: number;
  responseStatus?: number;
  responseCharacters?: number;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
};

export const MODEL_TIMING_MAX_PAGE_NUMBERS = 16;

const SAFE_NUMERIC_FIELDS = [
  "batchIndex",
  "totalBatches",
  "pageNumber",
  "batchPageCount",
  "inputCharacters",
  "requestHeadersWaitMs",
  "requestElapsedMs",
  "responseBodyAndEnvelopeMs",
  "jsonParseMs",
  "responseStatus",
  "responseCharacters",
  "promptTokens",
  "completionTokens",
  "totalTokens",
] as const;

const SAFE_ENUM_FIELDS = ["failureKind"] as const;

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
  const safe: Record<string, string | number | number[]> = {
    phase: event.phase,
    requestKind: event.requestKind,
  };
  if (Array.isArray(event.pageNumbers)
    && event.pageNumbers.length > 0
    && event.pageNumbers.length <= MODEL_TIMING_MAX_PAGE_NUMBERS
    && event.pageNumbers.every((page, index, pages) => Number.isSafeInteger(page) && page > 0 && pages.indexOf(page) === index)) {
    safe.pageNumbers = [...event.pageNumbers];
  }
  for (const field of SAFE_NUMERIC_FIELDS) {
    const value = event[field];
    if (typeof value === "number" && Number.isFinite(value)) safe[field] = value;
  }
  for (const field of SAFE_ENUM_FIELDS) {
    const value = event[field];
    if (typeof value === "string" && ["provider_busy", "provider_connection", "provider_timeout", "request_aborted", "other"].includes(value)) safe[field] = value;
  }
  logger(`[TCE_MODEL_TIMING] ${JSON.stringify(safe)}`);
}
