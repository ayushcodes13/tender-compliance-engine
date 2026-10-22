import { analyzeTender } from "../../actions";
import type { ProcessingProgress } from "../../processing-progress";

export const runtime = "nodejs";
export const maxDuration = 300;

type StreamEvent = { type: "progress"; progress: ProcessingProgress }
  | { type: "result"; result: Awaited<ReturnType<typeof analyzeTender>> };

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return Response.json({ error: "The uploaded form could not be read." }, { status: 400 });
  }

  const encoder = new TextEncoder();
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (event: StreamEvent) => {
        if (cancelled) return;
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        } catch {
          cancelled = true;
        }
      };
      void analyzeTender(form, (progress) => send({ type: "progress", progress }))
        .then((result) => send({ type: "result", result }))
        .catch(() => send({ type: "result", result: { ok: false as const, error: "The tender could not be processed. Please try again." } }))
        .finally(() => {
          if (cancelled) return;
          try {
            controller.close();
          } catch {
            cancelled = true;
          }
        });
    },
    cancel() {
      cancelled = true;
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
