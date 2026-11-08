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
 * unbounded body first. Content-Length is only an early rejection hint; the
 * streaming counter remains authoritative for missing or incorrect headers.
 */
export async function parseBoundedFormData(request: Request, maxBytes: number): Promise<FormData> {
  const contentLength = request.headers.get("content-length");
  if (contentLength && /^\d+$/.test(contentLength) && Number(contentLength) > maxBytes) {
    throw new RequestBodyTooLargeError();
  }

  if (!request.body) throw new TypeError("The request has no form body.");
  const reader = request.body.getReader();
  let received = 0;
  const boundedBody = new ReadableStream<Uint8Array>({
    async pull(controller) {
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
  return boundedRequest.formData();
}
