/** Maximum multipart metadata around the one accepted tender file. */
export const MAX_MULTIPART_OVERHEAD_BYTES = 256 * 1024;

export class RequestBodyTooLargeError extends Error {
  constructor() {
    super("The uploaded request is larger than the configured limit.");
    this.name = "RequestBodyTooLargeError";
  }
}

/**
 * Parse multipart form data without allowing Request.formData() to buffer an
 * unbounded body first. Content-Length is an early rejection hint; the
 * streaming counter remains authoritative when it is absent or incorrect.
 */
export async function parseBoundedFormData(request: Request, maxBytes: number): Promise<FormData> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) {
    throw new RangeError("The request body limit must be a positive safe integer.");
  }
  if (request.signal.aborted) throw request.signal.reason ?? new DOMException("The upload was cancelled.", "AbortError");

  const contentLength = request.headers.get("content-length");
  if (contentLength && /^\d+$/.test(contentLength) && Number(contentLength) > maxBytes) {
    await request.body?.cancel().catch(() => undefined);
    throw new RequestBodyTooLargeError();
  }

  if (!request.body) return new FormData();
  const reader = request.body.getReader();
  let received = 0;
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const abort = () => {
    const reason = request.signal.reason ?? new DOMException("The upload was cancelled.", "AbortError");
    void reader.cancel(reason).catch(() => undefined);
    try { streamController?.error(reason); } catch { /* The stream may already be closed. */ }
  };
  request.signal.addEventListener("abort", abort, { once: true });

  const boundedBody = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
    },
    async pull(controller) {
      if (request.signal.aborted) {
        controller.error(request.signal.reason ?? new DOMException("The upload was cancelled.", "AbortError"));
        return;
      }
      try {
        const chunk = await reader.read();
        if (chunk.done) {
          controller.close();
          return;
        }
        received += chunk.value.byteLength;
        if (received > maxBytes) {
          await reader.cancel();
          controller.error(new RequestBodyTooLargeError());
          return;
        }
        controller.enqueue(chunk.value);
      } catch (error) {
        controller.error(error);
      }
    },
    async cancel(reason) {
      await reader.cancel(reason);
    },
  });

  const boundedRequest = new Request(request.url, {
    method: request.method,
    headers: request.headers,
    body: boundedBody,
    signal: request.signal,
    duplex: "half",
  } as RequestInit & { duplex: "half" });
  try {
    const form = await boundedRequest.formData();
    if (request.signal.aborted) throw request.signal.reason ?? new DOMException("The upload was cancelled.", "AbortError");
    return form;
  } finally {
    request.signal.removeEventListener("abort", abort);
    reader.releaseLock();
  }
}
