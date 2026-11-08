import test from "node:test";
import assert from "node:assert/strict";
import { MAX_MULTIPART_OVERHEAD_BYTES, parseBoundedFormData, RequestBodyTooLargeError } from "./bounded-form-data.ts";

function multipartRequest(fields) {
  const form = new FormData();
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  const encoded = new Request("http://localhost/api/analyze", { method: "POST", body: form });
  return encoded;
}

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

test("enforces the limit while streaming if Content-Length is absent", async () => {
  const boundary = "bounded-test";
  const request = new Request("http://localhost/api/analyze", {
    method: "POST",
    headers: { "content-type": `multipart/form-data; boundary=${boundary}` },
    body: `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="tender.pdf"\r\nContent-Type: application/pdf\r\n\r\n${"x".repeat(4096)}\r\n--${boundary}--\r\n`,
  });
  await assert.rejects(parseBoundedFormData(request, 1024), RequestBodyTooLargeError);
});

test("multipart envelope allowance is explicit and bounded", () => {
  assert.equal(MAX_MULTIPART_OVERHEAD_BYTES, 256 * 1024);
});
