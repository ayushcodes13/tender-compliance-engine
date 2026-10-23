export type ProcessingStage = "uploading" | "reading" | "locating" | "mapping" | "extracting" | "coverage" | "verifying" | "preparing" | "complete" | "error" | "cancelled";
export type ProcessingProgress = { stage: ProcessingStage; message: string; current?: number; total?: number };

export const PROCESSING_STEPS: Array<{ id: Exclude<ProcessingStage, "error" | "cancelled">; label: string }> = [
  { id: "uploading", label: "Upload and validate the PDF" },
  { id: "reading", label: "Read pages and detect layouts" },
  { id: "locating", label: "Locate technical requirements" },
  { id: "mapping", label: "Identify columns and table structures" },
  { id: "extracting", label: "Extract requirements" },
  { id: "coverage", label: "Check page and row coverage" },
  { id: "verifying", label: "Verify source quotations" },
  { id: "preparing", label: "Prepare the response sheet" },
  { id: "complete", label: "Ready for review" },
];

export function processingStepIndex(stage: ProcessingStage): number {
  if (stage === "error" || stage === "cancelled") return -1;
  return PROCESSING_STEPS.findIndex((step) => step.id === stage);
}

export function formatElapsedSeconds(seconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return minutes ? `${minutes}:${String(remainingSeconds).padStart(2, "0")}` : `${remainingSeconds}s`;
}
