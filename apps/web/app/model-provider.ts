export type ModelProviderConfig = { provider: "openai-compatible"; baseUrl: string; model: string; apiKey: string };
export type ModelProviderResult = { ok: true; config: ModelProviderConfig } | { ok: false; error: string };
type Environment = Record<string, string | undefined>;
type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export const MODEL_REQUESTS_PER_ANALYSIS = 3;

export class ModelProviderConnectionError extends Error {
  constructor() {
    super("Could not reach the configured GPT-6 Luna endpoint. Check the network connection and retry.");
    this.name = "ModelProviderConnectionError";
  }
}

export class ModelProviderBusyError extends Error {
  constructor() {
    super("The extraction service is busy. Please retry shortly.");
    this.name = "ModelProviderBusyError";
  }
}

export class ModelProviderTimeoutError extends Error {
  constructor() {
    super("A GPT-6 Luna request exceeded its 90-second provider execution limit. The timed-out request was not automatically retried.");
    this.name = "ModelProviderTimeoutError";
  }
}

export type ModelRequestAdmission = {
  acquire(signal: AbortSignal | undefined, clientKey: object, clientLimit: number): Promise<() => void>;
};

/** Process-local guard shared by analyses in one running app instance. */
export function createModelRequestAdmission(options: { maxConcurrent?: number; maxQueued?: number; queueTimeoutMs?: number } = {}): ModelRequestAdmission {
  const maxConcurrent = options.maxConcurrent ?? 6;
  const maxQueued = options.maxQueued ?? 24;
  const queueTimeoutMs = options.queueTimeoutMs ?? 30_000;
  if (!Number.isInteger(maxConcurrent) || maxConcurrent < 1 || !Number.isInteger(maxQueued) || maxQueued < 0 || queueTimeoutMs < 1) {
    throw new Error("Model request admission limits must be positive integers.");
  }
  let active = 0;
  type Waiter = { grant: (release: () => void) => void; reject: (error: unknown) => void; signal?: AbortSignal; timer: ReturnType<typeof setTimeout>; abort: () => void; clientKey: object; clientLimit: number };
  const queue: Waiter[] = [];
  const activeByClient = new Map<object, number>();
  const releaseFor = (clientKey: object) => {
    active -= 1;
    const clientActive = activeByClient.get(clientKey) ?? 0;
    if (clientActive <= 1) activeByClient.delete(clientKey);
    else activeByClient.set(clientKey, clientActive - 1);
    dispatch();
  };
  const remove = (waiter: Waiter) => {
    const index = queue.indexOf(waiter);
    if (index >= 0) queue.splice(index, 1);
    clearTimeout(waiter.timer);
    waiter.signal?.removeEventListener("abort", waiter.abort);
  };
  const dispatch = () => {
    while (active < maxConcurrent && queue.length) {
      const index = queue.findIndex((candidate) => (activeByClient.get(candidate.clientKey) ?? 0) < candidate.clientLimit);
      if (index < 0) return;
      const [waiter] = queue.splice(index, 1);
      clearTimeout(waiter.timer);
      waiter.signal?.removeEventListener("abort", waiter.abort);
      if (waiter.signal?.aborted) { waiter.reject(waiter.signal.reason); continue; }
      active += 1;
      activeByClient.set(waiter.clientKey, (activeByClient.get(waiter.clientKey) ?? 0) + 1);
      waiter.grant(() => releaseFor(waiter.clientKey));
    }
  };
  return {
    acquire(signal, clientKey, clientLimit) {
      signal?.throwIfAborted();
      if (!Number.isInteger(clientLimit) || clientLimit < 1) return Promise.reject(new Error("The per-analysis model limit must be a positive integer."));
      if (active < maxConcurrent && queue.length === 0 && (activeByClient.get(clientKey) ?? 0) < clientLimit) {
        active += 1;
        activeByClient.set(clientKey, (activeByClient.get(clientKey) ?? 0) + 1);
        return Promise.resolve(() => releaseFor(clientKey));
      }
      if (queue.length >= maxQueued) return Promise.reject(new ModelProviderBusyError());
      return new Promise((resolve, reject) => {
        const waiter: Waiter = {
          grant: (release) => resolve(release),
          reject,
          signal,
          clientKey,
          clientLimit,
          timer: setTimeout(() => { remove(waiter); reject(new ModelProviderBusyError()); }, queueTimeoutMs),
          abort: () => { remove(waiter); reject(signal?.reason); },
        };
        queue.push(waiter);
        signal?.addEventListener("abort", waiter.abort, { once: true });
        if (signal?.aborted) waiter.abort();
      });
    },
  };
}

const processModelRequestAdmission = createModelRequestAdmission();

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
export function createModelCompletionClient(
  config: ModelProviderConfig,
  fetcher: FetchLike = fetch,
  options: { maxConcurrent?: number; executionTimeoutMs?: number; admission?: ModelRequestAdmission } = {},
) {
  const maxConcurrent = options.maxConcurrent ?? MODEL_REQUESTS_PER_ANALYSIS;
  const executionTimeoutMs = options.executionTimeoutMs ?? 90_000;
  const admission = options.admission ?? processModelRequestAdmission;
  const clientKey = {};
  return {
    async fetch(_input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
      if (init?.method && init.method.toUpperCase() !== "POST") throw new Error("Model completion requests must use POST.");
      if (init?.body !== undefined && typeof init.body !== "string") throw new Error("Model completion request body must be JSON text.");
      const cancellationSignal = init?.signal ?? undefined;
      let releaseAdmission: (() => void) | undefined;
      try {
        releaseAdmission = await admission.acquire(cancellationSignal, clientKey, maxConcurrent);
        const executionTimeout = AbortSignal.timeout(executionTimeoutMs);
        const requestSignal = cancellationSignal
          ? AbortSignal.any([cancellationSignal, executionTimeout])
          : executionTimeout;
        let lastError: unknown;
        for (let attempt = 0; attempt < 3; attempt += 1) {
          try {
            requestSignal.throwIfAborted();
            const response = await fetcher(`${config.baseUrl}/chat/completions`, {
              method: "POST",
              headers: new Headers({ "Content-Type": "application/json", Authorization: `Bearer ${config.apiKey}` }),
              signal: requestSignal,
              body: init?.body,
            });
            if (response.status === 408 || response.status === 504) throw new ModelProviderTimeoutError();
            if (response.status === 429) {
              if (attempt < 2) {
                await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
                continue;
              }
            }
            return response;
          } catch (error) {
            lastError = error;
            if (executionTimeout.aborted && !cancellationSignal?.aborted) throw new ModelProviderTimeoutError();
            if (cancellationSignal?.aborted) throw cancellationSignal.reason ?? error;
            if (error instanceof DOMException && error.name === "AbortError") throw error;
            if (error instanceof TypeError) throw new ModelProviderConnectionError();
            if (attempt < 2 && error instanceof Error && error.name === "AbortError" && !requestSignal.aborted) {
              await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
              continue;
            }
            throw error;
          }
        }
        if (lastError instanceof TypeError) throw new ModelProviderConnectionError();
        throw lastError;
      } finally {
        releaseAdmission?.();
      }
    },
  };
}
