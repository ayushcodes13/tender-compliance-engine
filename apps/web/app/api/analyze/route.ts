import { analyzeTender } from "../../actions";
import { createAnalysisResponse } from "../../analysis-stream";

export const runtime = "nodejs";
export const maxDuration = 300;
// Leave ten seconds for stream completion and cleanup before the function cap.
const ANALYSIS_DEADLINE_MS = 290_000;

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return Response.json({ error: "The uploaded form could not be read." }, { status: 400 });
  }

  return createAnalysisResponse(
    (signal, onProgress) => analyzeTender(form, onProgress, signal),
    request.signal,
    ANALYSIS_DEADLINE_MS,
  );
}
