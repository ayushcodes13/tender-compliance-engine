export type ModelProviderConfig = { provider: "openai-compatible"; baseUrl: string; model: string; apiKey: string };
export type ModelProviderResult = { ok: true; config: ModelProviderConfig } | { ok: false; error: string };
type Environment = Record<string, string | undefined>;
type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class ModelProviderConnectionError extends Error {
  constructor() {
    super("Could not reach the configured GPT-6 Luna endpoint. Check the network connection and retry.");
    this.name = "ModelProviderConnectionError";
  }
}

export function resolveModelProvider(env: Environment): ModelProviderResult {
  const apiKey = env.OPENAI_API_KEY?.trim();
  if (!apiKey) return { ok: false, error: "GPT-6 Luna is not configured. Add OPENAI_API_KEY to apps/web/.env.local." };
  const baseUrl = (env.OPENAI_BASE_URL?.trim() || "https://api.openai.com/v1").replace(/\/+$/, "");
  try {
    const url = new URL(baseUrl);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error();
  } catch {
    return { ok: false, error: "OPENAI_BASE_URL must be a valid HTTP or HTTPS endpoint without embedded credentials." };
  }
  const model = env.OPENAI_MODEL?.trim() || "gpt-6-luna";
  if (model.toLocaleLowerCase() !== "gpt-6-luna") return { ok: false, error: "This service is configured to use GPT-6 Luna only; set OPENAI_MODEL=gpt-6-luna." };
  return { ok: true, config: { provider: "openai-compatible", baseUrl, model, apiKey } };
}

/** Per-analysis admission control: pages/crops cannot flood the provider. */
export function createModelCompletionClient(config: ModelProviderConfig, fetcher: FetchLike = fetch) {
  let active = 0;
  const queue: Array<() => void> = [];
  const acquire = async (signal: AbortSignal) => {
    signal.throwIfAborted();
    if (active < 3) { active += 1; return; }
    await new Promise<void>((resolve, reject) => {
      const granted = () => { signal.removeEventListener("abort", aborted); resolve(); };
      const aborted = () => {
        const index = queue.indexOf(granted);
        if (index >= 0) queue.splice(index, 1);
        reject(signal.reason);
      };
      queue.push(granted);
      signal.addEventListener("abort", aborted, { once: true });
    });
  };
  const release = () => {
    const next = queue.shift();
    if (next) next();
    else active -= 1;
  };
  return {
    async fetch(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
      if (init?.method && init.method.toUpperCase() !== "POST") throw new Error("Model completion requests must use POST.");
      if (init?.body !== undefined && typeof init.body !== "string") throw new Error("Model completion request body must be JSON text.");
      const signal = init?.signal ?? AbortSignal.timeout(180_000);
      await acquire(signal);
      try {
        signal.throwIfAborted();
        return await fetcher(`${config.baseUrl}/chat/completions`, {
          method: "POST",
          headers: new Headers({ "Content-Type": "application/json", Authorization: `Bearer ${config.apiKey}` }),
          signal,
          body: init?.body,
        });
      } catch (error) {
        if (error instanceof TypeError) throw new ModelProviderConnectionError();
        throw error;
      } finally { release(); }
    },
  };
}
