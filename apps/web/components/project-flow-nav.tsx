"use client";

import { Check, FileText, FileCheck2, SearchCheck } from "lucide-react";
import Link from "next/link";

type FlowStep = "tender" | "review" | "response";

const steps = [
  { id: "tender" as const, label: "Tender", icon: FileText },
  { id: "review" as const, label: "Review specifications", icon: SearchCheck },
  { id: "response" as const, label: "OEM response sheet", icon: FileCheck2 },
];

export function ProjectFlowNav(props: {
  projectId: string;
  current: FlowStep;
  tenderReady: boolean;
}) {
  const { projectId, current, tenderReady } = props;
  const currentIndex = steps.findIndex((step) => step.id === current);

  const hrefFor = (step: FlowStep) => {
    if (step === "tender") return `/projects/${projectId}#tender-sources`;
    if (step === "review") return `/projects/${projectId}/review`;
    return `/projects/${projectId}/matrix`;
  };

  const enabled = (step: FlowStep) => {
    return step === "tender" || tenderReady;
  };

  const completed = (step: FlowStep, index: number) => {
    if (step === "tender") return tenderReady;
    return index < currentIndex;
  };

  return (
    <nav className="project-flow-nav" aria-label="Tender response sheet workflow">
      {steps.map((step, index) => {
        const Icon = step.icon;
        const isCurrent = step.id === current;
        const isEnabled = enabled(step.id);
        const isComplete = completed(step.id, index);
        const className = [
          "project-flow-step",
          isCurrent ? "project-flow-step-current" : "",
          isComplete ? "project-flow-step-complete" : "",
          !isEnabled ? "project-flow-step-disabled" : "",
        ]
          .filter(Boolean)
          .join(" ");

        const content = (
          <>
            <span className="project-flow-icon" aria-hidden="true">
              {isComplete ? <Check size={14} /> : <Icon size={15} />}
            </span>
            <span className="project-flow-copy">
              <small>Step {index + 1}</small>
              <strong>{step.label}</strong>
            </span>
          </>
        );

        return isEnabled ? (
          <Link
            key={step.id}
            href={hrefFor(step.id)}
            className={className}
            aria-current={isCurrent ? "step" : undefined}
          >
            {content}
          </Link>
        ) : (
          <span key={step.id} className={className} aria-disabled="true">
            {content}
          </span>
        );
      })}
    </nav>
  );
}
