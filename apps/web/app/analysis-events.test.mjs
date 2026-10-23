import assert from "node:assert/strict";
import test from "node:test";
import { consumeAnalysisStream, PROGRESS_STAGE_ORDER } from "./analysis-events.ts";
import { PROCESSING_STEPS } from "./processing-progress.ts";

function streamResponse(chunks, { failure } = {}) {
  let index = 0;
  return new Response(new ReadableStream({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(new TextEncoder().encode(chunks[index++]));
      } else if (failure) {
        controller.error(failure);
      } else {
        controller.close();
      }
    },
  }));
}

const progress = (stage, message, current, total) => `data: ${JSON.stringify({
  type: "progress",
  progress: { stage, message, current, total },
})}\n\n`;

test("stream stage ordering matches the visible progress steps", () => {
  assert.deepEqual(PROGRESS_STAGE_ORDER, PROCESSING_STEPS.map((step) => step.id));
  assert.equal(PROGRESS_STAGE_ORDER.at(-1), "complete");
});

test("parses events fragmented across arbitrary UTF-8 stream chunks", async () => {
  const text = `${progress("reading", "Reading café · page 1", 1, 2)}data: ${JSON.stringify({ type: "result", result: { ok: true } })}\n\n`;
  const bytes = new TextEncoder().encode(text);
  const chunks = Array.from(bytes, (byte) => Uint8Array.of(byte));
  const response = new Response(new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk));
      controller.close();
    },
  }));
  const observed = [];
  const result = await consumeAnalysisStream(response, { onProgress: (value) => observed.push(value) });
  assert.deepEqual(observed, [{ stage: "reading", message: "Reading café · page 1", current: 1, total: 2 }]);
  assert.deepEqual(result, { ok: true });
});

test("ignores duplicate and stale progress and stops after the first terminal event", async () => {
  const events = [
    progress("reading", "Reading pages", 2, 4),
    progress("reading", "Reading pages", 2, 4),
    progress("locating", "Locating requirements", 1, 1),
    progress("reading", "Late page event", 4, 4),
    progress("extracting", "Extracting rows", 0, 3),
    `data: ${JSON.stringify({ type: "result", result: "finished" })}\n\n`,
    progress("verifying", "Late verification event", 3, 3),
    `data: ${JSON.stringify({ type: "result", result: "duplicate" })}\n\n`,
  ];
  const observed = [];
  const result = await consumeAnalysisStream(streamResponse(events), { onProgress: (value) => observed.push(value) });
  assert.deepEqual(observed.map(({ stage }) => stage), ["reading", "locating", "extracting"]);
  assert.equal(result, "finished");
});

test("reports an interrupted stream as retryable instead of presenting completion", async () => {
  const response = streamResponse([progress("extracting", "Extracting rows", 1, 3)], { failure: new Error("socket disconnected") });
  const observed = [];
  await assert.rejects(consumeAnalysisStream(response, { onProgress: (value) => observed.push(value) }), /socket disconnected/);
  assert.equal(observed.length, 1);
});

test("cancelling an in-flight stream releases the reader and preserves cancellation", async () => {
  let sourceCancelled = false;
  const response = new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode(progress("extracting", "Extracting rows", 1, 3))); },
    cancel() { sourceCancelled = true; },
  }));
  const abortController = new AbortController();
  const pending = consumeAnalysisStream(response, { onProgress: () => {}, signal: abortController.signal });
  await new Promise((resolve) => setTimeout(resolve, 0));
  abortController.abort("user cancelled");
  await assert.rejects(pending, /user cancelled/);
  assert.equal(sourceCancelled, true);
});

test("surfaces an application error and suppresses later events", async () => {
  const response = streamResponse([
    `data: ${JSON.stringify({ type: "error", error: "Try again" })}\n\n`,
    progress("complete", "Should not be applied", 1, 1),
  ]);
  const observed = [];
  await assert.rejects(consumeAnalysisStream(response, { onProgress: (value) => observed.push(value) }), /Try again/);
  assert.deepEqual(observed, []);
});

test("fails safely on malformed event JSON", async () => {
  const response = streamResponse(["data: {not-json}\n\n"]);
  await assert.rejects(
    consumeAnalysisStream(response, { onProgress: () => {} }),
    /invalid progress event\. Please retry/,
  );
});
