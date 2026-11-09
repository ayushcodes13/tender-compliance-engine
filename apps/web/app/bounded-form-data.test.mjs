import test from "node:test";
import assert from "node:assert/strict";
import { MAX_MULTIPART_OVERHEAD_BYTES, parseBoundedFormData, RequestBodyTooLargeError } from "./bounded-form-data.ts";

function multipartRequest(fields) {
  const form = new FormData();
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  return new Request("http://localhost/api/analyze", { method: "POST", body: form });
}

test("parses a multipart request containing the full 32 MB tender allowance", async () => {
  const tender = new Blob([new Uint8Array(32 * 1024 * 1024)]);
  const request = multipartRequest({ file: tender });
  const parsed = await parseBoundedFormData(request, 32 * 1024 * 1024 + MAX_MULTIPART_OVERHEAD_BYTES);
  assert.equal(parsed.get("file").size, 32 * 1024 * 1024);
});

test("parses multipart form data within the configured request byte limit", async () => {
  const request = multipartRequest({ file: new Blob(["%PDF-1.7 test"]) });
  const parsed = await parseBoundedFormData(request, 1024);
  assert.equal(await parsed.get("file").text(), "%PDF-1.7 test");
});

test("rejects an oversized Content-Length before consuming the body", async () => {
  const request = new Request("http://localhost/api/analyze", {
    method: "POST",
    headers: { "content-type": "multipart/form-data; boundary=x", "content-length": "100" },
    body: "",
  });
  await assert.rejects(parseBoundedFormData(request, 99), RequestBodyTooLargeError);
});

test("enforces the request limit while streaming when Content-Length is absent", async () => {
  const boundary = "bounded-test";
  const request = new Request("http://localhost/api/analyze", {
    method: "POST",
    headers: { "content-type": `multipart/form-data; boundary=${boundary}` },
    body: `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="tender.pdf"\r\nContent-Type: application/pdf\r\n\r\n${"x".repeat(4096)}\r\n--${boundary}--\r\n`,
  });
  await assert.rejects(parseBoundedFormData(request, 1024), RequestBodyTooLargeError);
});

test("propagates caller cancellation and releases the source reader", async () => {
  const controller = new AbortController();
  let cancelled = false;
  const body = new ReadableStream({
    pull() {},
    cancel() { cancelled = true; },
  });
  const request = new Request("http://localhost/api/analyze", {
    method: "POST",
    headers: { "content-type": "multipart/form-data; boundary=unused" },
    body,
    signal: controller.signal,
    duplex: "half",
  });
  const pending = parseBoundedFormData(request, 1024);
  controller.abort(new DOMException("cancelled", "AbortError"));
  await assert.rejects(pending, /cancelled/i);
  assert.equal(cancelled, true);
});

test("rejects invalid byte limits instead of silently disabling the bound", async () => {
  await assert.rejects(parseBoundedFormData(new Request("http://localhost"), 0), RangeError);
});

test("multipart envelope allowance is explicit and bounded", () => {
  assert.equal(MAX_MULTIPART_OVERHEAD_BYTES, 256 * 1024);
});
