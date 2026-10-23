import type { ProcessingProgress } from "./processing-progress";

type StreamEvent<T> = { type: "progress"; progress: ProcessingProgress }
  | { type: "result"; result: T }
  | { type: "error"; error: string };

export function createAnalysisResponse<T>(
  analyze: (signal: AbortSignal, onProgress: (progress: ProcessingProgress) => void) => Promise<T>,
  requestSignal?: AbortSignal,
): Response {
  const analysisController = new AbortController();
  let cancelled = false;
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const cancel = (reason?: unknown, closeStream = false) => {
    if (cancelled) return;
    cancelled = true;
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
      void analyze(analysisController.signal, (progress) => send({ type: "progress", progress }))
        .then((result) => send({ type: "result", result }))
        .catch(() => {
          if (!analysisController.signal.aborted) send({ type: "error", error: "The tender could not be processed. Please try again." });
        })
        .finally(() => {
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
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
