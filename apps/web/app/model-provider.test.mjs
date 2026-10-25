import test from "node:test";
import assert from "node:assert/strict";
import { createModelCompletionClient, ModelProviderConnectionError, resolveModelProvider } from "./model-provider.ts";

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
  const requests = Array.from({length:3},()=>client.fetch('ignored'));
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
  assert.equal(peak,3);
  assert.equal(sent,4);
});
