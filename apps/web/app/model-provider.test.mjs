import test from "node:test";
import assert from "node:assert/strict";
import { createModelCompletionClient, createModelRequestAdmission, ModelProviderBusyError, ModelProviderConnectionError, ModelProviderTimeoutError, resolveModelProvider } from "./model-provider.ts";

test("selects GPT-6 Luna by default when the local key is present", () => {
  assert.deepEqual(resolveModelProvider({ OPENAI_API_KEY: "secret", OPENAI_BASE_URL: "https://example.invalid/openai/v1" }), {
    ok: true,
    config: { provider: "openai-compatible", baseUrl: "https://example.invalid/openai/v1", model: "gpt-6-luna", apiKey: "secret" },
  });
});

test("fails clearly when GPT-6 Luna credentials are missing", () => {
  const result = resolveModelProvider({});
  assert.equal(result.ok, false);
  if (!result.ok) assert.match(result.error, /GPT-6 Luna is not configured/);
});

test("rejects other model names and malformed endpoints", () => {
  assert.equal(resolveModelProvider({ OPENAI_API_KEY: "x", OPENAI_MODEL: "gpt-4o" }).ok, false);
  assert.equal(resolveModelProvider({ OPENAI_API_KEY: "x", OPENAI_BASE_URL: "file:///tmp/model" }).ok, false);
});

test("sends the configured model request with the API key server-side", async () => {
  let request;
  const client = createModelCompletionClient({
    provider: "openai-compatible", baseUrl: "https://example.invalid/v1", model: "gpt-6-luna", apiKey: "secret",
  }, async (input, init) => {
    request = { input: String(input), init };
    return new Response("{}", { status: 200 });
  });
  const response = await client.fetch("https://ignored.invalid/chat/completions", { method: "POST", body: "{}" });
  assert.equal(response.status, 200);
  assert.equal(request.input, "https://example.invalid/v1/chat/completions");
  assert.equal(new Headers(request.init.headers).get("authorization"), "Bearer secret");
});

test("turns a network failure into a safe endpoint connection message", async () => {
  const client = createModelCompletionClient({
    provider: "openai-compatible", baseUrl: "https://example.invalid/v1", model: "gpt-6-luna", apiKey: "secret",
  }, async () => { throw new TypeError("internal networking details"); });
  await assert.rejects(client.fetch("https://ignored.invalid/chat/completions", { method: "POST", body: "{}" }), (error) => {
    assert.equal(error instanceof ModelProviderConnectionError, true);
    assert.match(error.message, /Could not reach the configured GPT-6 Luna endpoint/);
    assert.doesNotMatch(error.message, /internal networking details|secret/);
    return true;
  });
});

test('bounds in-flight requests and never sends aborted queued work', async () => {
  let active = 0;
  let peak = 0;
  let sent = 0;
  const releaseRequests = [];
  const client = createModelCompletionClient({provider:'openai-compatible',baseUrl:'https://example.invalid',model:'gpt-6-luna',apiKey:'secret'}, async () => {
    sent++; active++; peak=Math.max(peak,active);
    await new Promise(resolve=>releaseRequests.push(resolve));
    active--; return new Response('{}');
  });
  const requests = Array.from({length:6},()=>client.fetch('ignored'));
  await new Promise(resolve=>setImmediate(resolve));
  const controller = new AbortController();
  const queued = client.fetch('ignored',{signal:controller.signal});
  controller.abort();
  await assert.rejects(queued, {name:'AbortError'});
  const final = client.fetch('ignored');
  releaseRequests.splice(0).forEach(resolve=>resolve());
  await Promise.all(requests);
  await new Promise(resolve=>setImmediate(resolve));
  releaseRequests.splice(0).forEach(resolve=>resolve());
  await final;
  assert.equal(peak,6);
  assert.equal(sent,7);
});

test('starts the execution timeout only after a queued request is admitted', async () => {
  const admissions = [];
  const releaseRequests = [];
  const client = createModelCompletionClient(
    { provider: 'openai-compatible', baseUrl: 'https://example.invalid', model: 'gpt-6-luna', apiKey: 'secret' },
    async (_input, init) => {
      admissions.push(init.signal);
      await new Promise((resolve) => releaseRequests.push(resolve));
      return new Response('{}');
    },
    { maxConcurrent: 1, executionTimeoutMs: 500 },
  );
  const first = client.fetch('ignored');
  await new Promise((resolve) => setImmediate(resolve));
  const queued = client.fetch('ignored');
  await new Promise((resolve) => setTimeout(resolve, 350));
  releaseRequests.shift()();
  while (admissions.length < 2) await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setTimeout(resolve, 200));
  assert.equal(admissions[1].aborted, false, 'queued time did not consume its execution window');
  releaseRequests.shift()();
  await Promise.all([first, queued]);
});

test('reports provider execution timeout distinctly and never retries an ambiguous timed-out POST', async () => {
  let sent = 0;
  const client = createModelCompletionClient(
    { provider: 'openai-compatible', baseUrl: 'https://example.invalid', model: 'gpt-6-luna', apiKey: 'secret' },
    async (_input, init) => {
      sent += 1;
      return new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => setTimeout(() => reject(init.signal.reason), 0), { once: true }));
    },
    { executionTimeoutMs: 20 },
  );
  const request = assert.rejects(client.fetch('ignored', { method: 'POST', body: '{}' }), (error) => error instanceof ModelProviderTimeoutError);
  await Promise.all([request, new Promise((resolve) => setTimeout(resolve, 35))]);
  assert.equal(sent, 1);
});

test('does not resend a generation POST after an upstream gateway timeout response', async () => {
  let sent = 0;
  const client = createModelCompletionClient(
    { provider: 'openai-compatible', baseUrl: 'https://example.invalid', model: 'gpt-6-luna', apiKey: 'secret' },
    async () => { sent += 1; return new Response('{}', { status: 504 }); },
  );
  await assert.rejects(client.fetch('ignored', { method: 'POST', body: '{}' }), (error) => {
    assert.equal(error instanceof ModelProviderTimeoutError, true);
    assert.match(error.message, /gateway returned a timeout response/i);
    return true;
  });
  assert.equal(sent, 1);
});

test('does not retry an ambiguous upstream AbortError when the caller did not abort', async () => {
  let sent = 0;
  const client = createModelCompletionClient(
    { provider: 'openai-compatible', baseUrl: 'https://example.invalid', model: 'gpt-6-luna', apiKey: 'secret' },
    async () => {
      sent += 1;
      throw new DOMException('upstream stopped unexpectedly', 'AbortError');
    },
  );
  await assert.rejects(client.fetch('ignored', { method: 'POST', body: '{}' }), { name: 'AbortError' });
  assert.equal(sent, 1, 'an ambiguous failed generation request is never resent');
});

test('propagates caller cancellation without misreporting a provider timeout', async () => {
  let sent = 0;
  const client = createModelCompletionClient(
    { provider: 'openai-compatible', baseUrl: 'https://example.invalid', model: 'gpt-6-luna', apiKey: 'secret' },
    async (_input, init) => {
      sent += 1;
      return new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => setTimeout(() => reject(init.signal.reason), 0), { once: true }));
    },
    { executionTimeoutMs: 1_000 },
  );
  const controller = new AbortController();
  const request = client.fetch('ignored', { method: 'POST', body: '{}', signal: controller.signal });
  await new Promise((resolve) => setImmediate(resolve));
  controller.abort(new DOMException('cancelled', 'AbortError'));
  await assert.rejects(request, { name: 'AbortError' });
  assert.equal(sent, 1);
});

test('shares a bounded model-request limit across independent analyses', async () => {
  const admission = createModelRequestAdmission({ maxConcurrent: 1, maxQueued: 2, queueTimeoutMs: 1_000 });
  let active = 0;
  let peak = 0;
  const releases = [];
  const fetcher = async () => {
    active += 1;
    peak = Math.max(peak, active);
    await new Promise((resolve) => releases.push(resolve));
    active -= 1;
    return new Response('{}');
  };
  const config = { provider: 'openai-compatible', baseUrl: 'https://example.invalid', model: 'gpt-6-luna', apiKey: 'secret' };
  const firstClient = createModelCompletionClient(config, fetcher, { admission });
  const secondClient = createModelCompletionClient(config, fetcher, { admission });
  const first = firstClient.fetch('ignored');
  await new Promise((resolve) => setImmediate(resolve));
  const second = secondClient.fetch('ignored');
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(active, 1, 'the second analysis waits behind the shared process limit');
  releases.shift()();
  while (releases.length === 0) await new Promise((resolve) => setImmediate(resolve));
  releases.shift()();
  await Promise.all([first, second]);
  assert.equal(peak, 1);
});

test('rejects work when the shared model queue is full or its wait deadline expires', async () => {
  const admission = createModelRequestAdmission({ maxConcurrent: 1, maxQueued: 1, queueTimeoutMs: 25 });
  let release;
  const fetcher = () => new Promise((resolve) => { release = () => resolve(new Response('{}')); });
  const config = { provider: 'openai-compatible', baseUrl: 'https://example.invalid', model: 'gpt-6-luna', apiKey: 'secret' };
  const firstClient = createModelCompletionClient(config, fetcher, { admission });
  const secondClient = createModelCompletionClient(config, fetcher, { admission });
  const thirdClient = createModelCompletionClient(config, fetcher, { admission });
  const first = firstClient.fetch('ignored');
  await new Promise((resolve) => setImmediate(resolve));
  const queued = secondClient.fetch('ignored');
  await new Promise((resolve) => setImmediate(resolve));
  await assert.rejects(thirdClient.fetch('ignored'), (error) => error instanceof ModelProviderBusyError);
  await assert.rejects(queued, (error) => error instanceof ModelProviderBusyError);
  release();
  await first;
});
