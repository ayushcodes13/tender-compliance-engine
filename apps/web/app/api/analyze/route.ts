import { analyzeTender } from "../../actions";
import { createAnalysisResponse } from "../../analysis-stream";
import { MAX_MULTIPART_OVERHEAD_BYTES, parseBoundedFormData, RequestBodyTooLargeError } from "../../bounded-form-data";
import { resolveMaxFileBytes } from "../../upload-limits";

export const runtime = "nodejs";
export const maxDuration = 300;
// Leave ten seconds for stream completion and cleanup before the function cap.
const ANALYSIS_DEADLINE_MS = 290_000;

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await parseBoundedFormData(request, resolveMaxFileBytes() + MAX_MULTIPART_OVERHEAD_BYTES);
  } catch (error) {
    if (error instanceof RequestBodyTooLargeError) {
      return Response.json({ error: "The uploaded request exceeds the configured size limit." }, { status: 413 });
    }
    return Response.json({ error: "The uploaded form could not be read." }, { status: 400 });
  }

  return createAnalysisResponse(
    (signal, onProgress) => analyzeTender(form, onProgress, signal),
    request.signal,
    ANALYSIS_DEADLINE_MS,
  );
}
