export type ProcessingStage = "reading" | "locating" | "mapping" | "extracting" | "verifying" | "complete" | "error";
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
  if (stage === "error") return -1;
  return PROCESSING_STEPS.findIndex((step) => step.id === stage);
}
