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

export function createModelCompletionClient(config: ModelProviderConfig, fetcher: FetchLike = fetch) {
  return {
    fetch(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
      if (init?.method && init.method.toUpperCase() !== "POST") return Promise.reject(new Error("Model completion requests must use POST."));
      if (init?.body !== undefined && typeof init.body !== "string") return Promise.reject(new Error("Model completion request body must be JSON text."));
      return fetcher(`${config.baseUrl}/chat/completions`, {
        method: "POST",
        headers: new Headers({ "Content-Type": "application/json", Authorization: `Bearer ${config.apiKey}` }),
        signal: init?.signal ?? AbortSignal.timeout(180_000),
        body: init?.body,
      }).catch((error: unknown) => {
        if (error instanceof TypeError) throw new ModelProviderConnectionError();
        throw error;
      });
    },
  };
}
