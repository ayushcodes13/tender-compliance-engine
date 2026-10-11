"use client";

import { Check, FileText, FileCheck2, SearchCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

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
  documentId?: string;
  version?: number;
}) {
  const { projectId, current, tenderReady, documentId, version } = props;
  const [reviewComplete, setReviewComplete] = useState(false);

  useEffect(() => {
    if (current === "tender" || !documentId || version === undefined) {
      setReviewComplete(false);
      return;
    }

    let active = true;
    setReviewComplete(false);
    void api.fetchReviewCounts(projectId, documentId, version)
      .then((counts) => {
        if (active) {
          setReviewComplete(counts.active > 0 && counts.reviewed === counts.active);
        }
      })
      .catch(() => {
        if (active) setReviewComplete(false);
      });

    return () => {
      active = false;
    };
  }, [current, documentId, projectId, version]);

  const hrefFor = (step: FlowStep) => {
    if (step === "tender") return `/projects/${projectId}#tender-sources`;
    if (step === "review") return `/projects/${projectId}/review`;
    return `/projects/${projectId}/matrix`;
  };

  const enabled = (step: FlowStep) => {
    return step === "tender" || tenderReady;
  };

  const completed = (step: FlowStep) => {
    if (step === "tender") return tenderReady;
    if (step === "review") return reviewComplete;
    return false;
  };

  return (
    <nav className="project-flow-nav" aria-label="Tender response sheet workflow">
      {steps.map((step, index) => {
        const Icon = step.icon;
        const isCurrent = step.id === current;
        const isEnabled = enabled(step.id);
        const isComplete = completed(step.id);
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
