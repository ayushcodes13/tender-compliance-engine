import type { ProcessingProgress } from "./processing-progress";

type StreamEvent<T> = { type: "progress"; progress: ProcessingProgress }
  | { type: "result"; result: T }
  | { type: "error"; error: string };

export function createAnalysisResponse<T>(
  analyze: (signal: AbortSignal, onProgress: (progress: ProcessingProgress) => void) => Promise<T>,
  requestSignal?: AbortSignal,
  analysisDeadlineMs = 270_000,
): Response {
  if (!Number.isInteger(analysisDeadlineMs) || analysisDeadlineMs < 1) {
    throw new Error("The analysis deadline must be a positive integer.");
  }
  const analysisController = new AbortController();
  let cancelled = false;
  let timedOut = false;
  let terminalSent = false;
  let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const cancel = (reason?: unknown, closeStream = false) => {
    if (cancelled) return;
    cancelled = true;
    if (deadlineTimer) clearTimeout(deadlineTimer);
    requestSignal?.removeEventListener("abort", onRequestAbort);
    analysisController.abort(reason);
    if (closeStream && streamController) {
      try {
        streamController.close();
      } catch {
        // The consumer may already have closed its side of the stream.
      }
    }
  };
  const onRequestAbort = () => cancel(requestSignal?.reason, true);

  if (requestSignal?.aborted) onRequestAbort();
  else requestSignal?.addEventListener("abort", onRequestAbort, { once: true });

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
      if (cancelled) {
        controller.close();
        return;
      }
      const send = (event: StreamEvent<T>) => {
        if (cancelled) return;
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        } catch {
          cancel();
        }
      };
      const sendTerminal = (event: Extract<StreamEvent<T>, { type: "result" | "error" }>) => {
        if (terminalSent) return;
        terminalSent = true;
        send(event);
      };
      deadlineTimer = setTimeout(() => {
        timedOut = true;
        analysisController.abort(new DOMException("The analysis deadline was exceeded.", "TimeoutError"));
        sendTerminal({ type: "error", error: "Analysis time limit reached. Processing is incomplete; no response sheet was produced. Try a shorter tender or technical section." });
        try {
          controller.close();
        } catch {
          cancel();
        }
      }, analysisDeadlineMs);
      void analyze(analysisController.signal, (progress) => send({ type: "progress", progress }))
        .then((result) => {
          if (!timedOut) sendTerminal({ type: "result", result });
        })
        .catch(() => {
          if (!timedOut && !analysisController.signal.aborted) {
            sendTerminal({ type: "error", error: "The tender could not be processed. Please try again." });
          }
        })
        .finally(() => {
          if (deadlineTimer) clearTimeout(deadlineTimer);
          requestSignal?.removeEventListener("abort", onRequestAbort);
          if (cancelled) return;
          try {
            controller.close();
          } catch {
            cancel();
          }
        });
    },
    cancel(reason) {
      cancel(reason);
      requestSignal?.removeEventListener("abort", onRequestAbort);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "private, no-store, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
