import type { ProcessingProgress } from "./processing-progress";

export type AnalysisEvent<T> =
  | { type: "progress"; progress: ProcessingProgress }
  | { type: "result"; result: T }
  | { type: "error"; error: string };

export type AnalysisStreamCallbacks<T> = {
  onProgress: (progress: ProcessingProgress) => void;
  signal?: AbortSignal;
};

export const PROGRESS_STAGE_ORDER: ProcessingProgress["stage"][] = ["uploading", "reading", "locating", "mapping", "extracting", "coverage", "verifying", "preparing", "complete"];

function parsePacket<T>(packet: string): AnalysisEvent<T> | null {
  const dataLines = packet.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).replace(/^ /, ""));
  if (!dataLines.length) return null;
  const parsed = JSON.parse(dataLines.join("\n")) as AnalysisEvent<T>;
  if (parsed?.type === "progress" && parsed.progress && typeof parsed.progress.message === "string") return parsed;
  if (parsed?.type === "result" && "result" in parsed) return parsed;
  if (parsed?.type === "error" && typeof parsed.error === "string") return parsed;
  return null;
}

export async function consumeAnalysisStream<T>(
  response: Response,
  callbacks: AnalysisStreamCallbacks<T>,
): Promise<T> {
  if (!response.ok) {
    const problem = await response.json().catch(() => null) as { error?: string } | null;
    throw new Error(problem?.error || "The extraction service could not start.");
  }
  if (!response.body) throw new Error("The extraction service did not return a progress stream. Please retry.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const seenProgress = new Set<string>();
  let buffer = "";
  let lastStageIndex = -1;
  const terminal: { current: { type: "result"; result: T } | { type: "error"; error: string } | null } = { current: null };
  const abortReader = () => { void reader.cancel(callbacks.signal?.reason).catch(() => undefined); };
  callbacks.signal?.addEventListener("abort", abortReader, { once: true });

  const accept = (packet: string) => {
    let event: AnalysisEvent<T> | null;
    try {
      event = parsePacket<T>(packet);
    } catch {
      throw new Error("The extraction service returned an invalid progress event. Please retry.");
    }
    if (!event || terminal.current) return;
    if (event.type === "progress") {
      const stageIndex = PROGRESS_STAGE_ORDER.indexOf(event.progress.stage);
      if (stageIndex < lastStageIndex || stageIndex < 0) return;
      const fingerprint = JSON.stringify(event.progress);
      if (seenProgress.has(fingerprint)) return;
      seenProgress.add(fingerprint);
      lastStageIndex = stageIndex;
      callbacks.onProgress(event.progress);
      return;
    }
    terminal.current = event;
  };

  try {
    while (true) {
      callbacks.signal?.throwIfAborted();
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const packets = buffer.split(/\r?\n\r?\n/);
      buffer = packets.pop() ?? "";
      packets.forEach(accept);
      if (done) break;
    }
    if (buffer.trim()) accept(buffer);
    callbacks.signal?.throwIfAborted();
  } catch (error) {
    try { await reader.cancel(error); } catch { /* The fetch may already have closed the body. */ }
    throw error;
  } finally {
    callbacks.signal?.removeEventListener("abort", abortReader);
    reader.releaseLock();
  }

  if (!terminal.current) throw new Error("The extraction stream ended before the tender was ready. Please retry.");
  if (terminal.current.type === "error") throw new Error(terminal.current.error || "The tender could not be processed. Please try again.");
  return terminal.current.result;
}
