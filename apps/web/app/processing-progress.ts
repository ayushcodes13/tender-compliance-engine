export type ProcessingStage = "reading" | "locating" | "mapping" | "extracting" | "verifying" | "complete" | "error" | "cancelled";
export type ProcessingProgress = { stage: ProcessingStage; message: string; current?: number; total?: number };

export const PROCESSING_STEPS: Array<{ id: Exclude<ProcessingStage, "complete" | "error">; label: string }> = [
  { id: "reading", label: "Read the PDF and page layout" },
  { id: "locating", label: "Locate the technical section" },
  { id: "mapping", label: "Map the tender’s columns" },
  { id: "extracting", label: "Extract rows and subpoints" },
  { id: "verifying", label: "Check each quote against its page" },
];

export function processingStepIndex(stage: ProcessingStage): number {
  if (stage === "complete") return PROCESSING_STEPS.length;
  if (stage === "error" || stage === "cancelled") return -1;
  return PROCESSING_STEPS.findIndex((step) => step.id === stage);
}

export function formatElapsedSeconds(seconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return minutes ? `${minutes}:${String(remainingSeconds).padStart(2, "0")}` : `${remainingSeconds}s`;
}
