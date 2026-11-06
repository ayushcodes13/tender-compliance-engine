import assert from "node:assert/strict";
import test from "node:test";
import { createAnalysisResponse } from "./analysis-stream.ts";

function parseEvents(value) {
  return value.trim().split(/\r?\n\r?\n/).map((packet) => JSON.parse(packet.slice(6)));
}

test("streams progress before the final analysis result", async () => {
  const response = createAnalysisResponse(async (_signal, report) => {
    report({ stage: "reading", message: "Reading page 1", current: 1, total: 2 });
    return { ok: true, requirements: 3 };
  });

  assert.equal(response.headers.get("content-type"), "text/event-stream; charset=utf-8");
  const events = parseEvents(await response.text());
  assert.deepEqual(events.map((event) => event.type), ["progress", "result"]);
  assert.deepEqual(events[0].progress, { stage: "reading", message: "Reading page 1", current: 1, total: 2 });
  assert.deepEqual(events[1].result, { ok: true, requirements: 3 });
});

test("cancelling the response aborts the active analysis and suppresses its result", async () => {
  let analysisSignal;
  let finishAnalysis;
  const response = createAnalysisResponse((signal, report) => new Promise((resolve) => {
    analysisSignal = signal;
    finishAnalysis = resolve;
    report({ stage: "extracting", message: "Extracting requirements" });
    signal.addEventListener("abort", () => resolve({ ok: false, error: "cancelled" }), { once: true });
  }));
  const reader = response.body.getReader();
  const firstEvent = await reader.read();
  assert.equal(new TextDecoder().decode(firstEvent.value).includes('"type":"progress"'), true);

  await reader.cancel("user cancelled");
  assert.equal(analysisSignal.aborted, true);
  finishAnalysis?.({ ok: true });
});

test("request abort propagates to analysis and closes the event stream", async () => {
  const requestController = new AbortController();
  let analysisSignal;
  const response = createAnalysisResponse((signal, report) => new Promise((resolve) => {
    analysisSignal = signal;
    report({ stage: "reading", message: "Reading PDF" });
    signal.addEventListener("abort", () => resolve({ ok: false, error: "cancelled" }), { once: true });
  }), requestController.signal);
  const reader = response.body.getReader();
  await reader.read();

  requestController.abort("request disconnected");
  const end = await reader.read();
  assert.equal(analysisSignal.aborted, true);
  assert.equal(end.done, true);
});

test("unexpected analysis exceptions become a safe stream error", async () => {
  const response = createAnalysisResponse(async () => { throw new Error("private parser detail"); });
  const [event] = parseEvents(await response.text());
  assert.deepEqual(event, { type: "error", error: "The tender could not be processed. Please try again." });
});

test("analysis deadline aborts work and emits an explicit incomplete terminal event", async () => {
  let analysisSignal;
  const response = createAnalysisResponse((signal) => new Promise((resolve) => {
    analysisSignal = signal;
    signal.addEventListener("abort", () => resolve({ ok: true, responseRows: 4 }), { once: true });
  }), undefined, 10);

  const events = parseEvents(await response.text());
  assert.equal(analysisSignal.aborted, true);
  assert.deepEqual(events, [{
    type: "error",
    error: "Analysis time limit reached. Processing is incomplete; no response sheet was produced. Try a shorter tender or technical section.",
  }]);
});

test("analysis deadline must be a positive integer", () => {
  assert.throws(() => createAnalysisResponse(async () => ({}), undefined, 0), /positive integer/);
  assert.throws(() => createAnalysisResponse(async () => ({}), undefined, 1.5), /positive integer/);
});

test("analysis deadline closes the stream even if work ignores abort temporarily", async () => {
  let analysisSignal;
  let finishAnalysis;
  const response = createAnalysisResponse((signal) => new Promise((resolve) => {
    analysisSignal = signal;
    finishAnalysis = resolve;
  }), undefined, 10);

  const events = parseEvents(await response.text());
  assert.equal(analysisSignal.aborted, true);
  assert.equal(events.length, 1);
  assert.equal(events[0].type, "error");
  assert.match(events[0].error, /incomplete; no response sheet was produced/);
  finishAnalysis?.({ ok: true, responseRows: 4 });
  await new Promise((resolve) => setImmediate(resolve));
});
