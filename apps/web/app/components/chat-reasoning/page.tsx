"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { UIDataTypes, UIMessagePart, UITools } from "ai";
import { Check } from "lucide-react";
import ChatReasoning from "@/components/ui/chat-reasoning";

const parts: UIMessagePart<UIDataTypes, UITools>[] = [
  {
    type: "reasoning",
    text: "The user is asking for the sum of the first six positive even numbers.",
  } as UIMessagePart<UIDataTypes, UITools>,
  {
    type: "tool-calculator",
    toolCallId: "call_1",
    state: "output-available",
    input: { numbers: [2, 4, 6, 8, 10, 12] },
    output: 42,
  } as unknown as UIMessagePart<UIDataTypes, UITools>,
  {
    type: "reasoning",
    text: "The calculator tool returned the answer 42. Let me return the answer to the user.",
  } as UIMessagePart<UIDataTypes, UITools>,
];

function renderMessagePart(
  part: UIMessagePart<UIDataTypes, UITools>,
  key: string | number,
) {
  if (part.type === "reasoning") {
    return (
      <p
        key={key}
        className="text-sm text-muted-foreground leading-relaxed py-1"
      >
        {part.text}
      </p>
    );
  }
  if (part.type.startsWith("tool-")) {
    return (
      <div
        key={key}
        className="flex items-center gap-1.5 text-sm text-muted-foreground py-1"
      >
        <Check className="size-4 text-accent" />
        <span>Used {part.type.replace("tool-", "")}</span>
      </div>
    );
  }
  return null;
}

export default function ChatReasoningDemo() {
  return (
    <div className="mx-auto w-full max-w-md p-4">
      <ChatReasoning
        partsInAccordion={parts}
        defaultValue="reasoning"
        renderMessagePart={renderMessagePart}
      />
    </div>
  );
}
