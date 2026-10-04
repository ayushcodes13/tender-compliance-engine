"use client";

import { useState, useEffect, useRef, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  BarChart3,
  Bot,
  Check,
  FileText,
  Send,
  Shield,
  User,
} from "lucide-react";
import type { UIDataTypes, UIMessagePart, UITools } from "ai";

import { AdvancedChatInput, type FileAttachment } from "@/components/ui/advanced-ai-chat-input";
import ChatReasoning from "@/components/ui/chat-reasoning";

interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  content: string;
  timestamp: Date;
  reasoningParts?: UIMessagePart<UIDataTypes, UITools>[];
}

// Mock reasoning parts for the compliance assistant
const mockReasoningParts: UIMessagePart<UIDataTypes, UITools>[] = [
  {
    type: "reasoning",
    text: "User is asking about compliance status for a specific tender requirement. Let me check the matrix for requirement RQ-047.",
  } as UIMessagePart<UIDataTypes, UITools>,
  {
    type: "tool-fetchRequirement",
    toolCallId: "call_47",
    state: "output-available",
    input: { requirementId: "RQ-047" },
    output: {
      id: "RQ-047",
      normalized_text:
        "The product shall operate in ambient temperatures from -20°C to +60°C.",
      review_status: "reviewed",
    },
  } as unknown as UIMessagePart<UIDataTypes, UITools>,
  {
    type: "reasoning",
    text: "Found the requirement. Now checking the evidence matrix for vendor spec comparison.",
  } as UIMessagePart<UIDataTypes, UITools>,
  {
    type: "tool-comparisonResult",
    toolCallId: "call_cmp_47",
    state: "output-available",
    input: { requirementId: "RQ-047" },
    output: {
      verdict: "non_compliant",
      vendor_value: 55,
      vendor_unit: "°C",
      upper_bound: 60,
      comparison_rule: "range_containment",
      reasons: [
        "Vendor max operating temperature (55°C) is below the tender requirement (60°C).",
      ],
    },
  } as unknown as UIMessagePart<UIDataTypes, UITools>,
  {
    type: "reasoning",
    text: "The vendor spec max temperature is 55°C, but the tender requires 60°C. This is a non-compliance gap. I should flag this for review.",
  } as UIMessagePart<UIDataTypes, UITools>,
];

const renderMessagePart = (
  part: UIMessagePart<UIDataTypes, UITools>,
  key: string | number,
): ReactNode => {
  if (part.type === "reasoning") {
    return (
      <p
        key={key}
        className="text-sm text-text-secondary leading-relaxed py-1"
      >
        {part.text}
      </p>
    );
  }
  if (part.type.startsWith("tool-")) {
    return (
      <div
        key={key}
        className="flex items-center gap-1.5 text-sm text-text-secondary py-1"
      >
        <Check className="size-4 text-accent" />
        <span>Used {part.type.replace("tool-", "")}</span>
      </div>
    );
  }
  return null;
};

export default function DashboardChatPage() {
  const [inputValue, setInputValue] = useState("");
  const [files, setFiles] = useState<FileAttachment[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "1",
      role: "assistant",
      content:
        "Hello! I'm your Compliance AI Assistant. I can help you understand tender requirements, find evidence, and check compliance status. I'm backed by deterministic math and source-linked evidence — I never fabricate citations or compliance verdicts.",
      timestamp: new Date(),
    },
  ]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!inputValue && files.length === 0) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Simulate AI response with reasoning
    setTimeout(() => {
      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content:
          "Based on the compliance matrix, requirement RQ-047 is currently **non-compliant**. The tender requires operation from -20°C to +60°C, but the vendor spec lists a maximum of 55°C. You should flag this for vendor clarification.",
        timestamp: new Date(),
        reasoningParts: mockReasoningParts,
      };
      setMessages((prev) => [...prev, aiMsg]);
    }, 1000);

    setInputValue("");
    setFiles([]);
  };

  const handleRemoveFile = (id: string | number) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const actionIcons = [
    <button
      key="document"
      className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary hover:bg-surface-elevated hover:text-text-primary"
      aria-label="Attach document"
      type="button"
    >
      <FileText className="h-4 w-4" />
    </button>,
    <button
      key="insight"
      className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary hover:bg-surface-elevated hover:text-text-primary"
      aria-label="Request insight"
      type="button"
    >
      <BarChart3 className="h-4 w-4" />
    </button>,
  ];

  return (
    <div className="flex h-[calc(100vh-12rem)] flex-col">
      {/* Messages */}
      <div
        ref={messagesEndRef}
        className="flex-1 space-y-4 overflow-y-auto"
      >
        <AnimatePresence>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              className={cn(
                "flex gap-2.5",
                msg.role === "user" ? "justify-end" : "justify-start",
              )}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              {msg.role === "assistant" && (
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <Bot className="h-4 w-4" />
                </div>
              )}
              <div
                className={cn(
                  "max-w-[75%] rounded-2xl px-4 py-3 text-sm",
                  msg.role === "user"
                    ? "bg-accent text-background"
                    : "border border-border bg-surface",
                )}
              >
                <div
                  className={cn(
                    "prose prose-sm max-w-none",
                    msg.role === "user" ? "prose-invert" : "prose-invert",
                  )}
                >
                  {msg.content.split("\n").map((line, i) => (
                    <p key={i} className="mb-1 last:mb-0">
                      {line.replace(/\*\*(.+?)\*\*/g, "$1")}
                    </p>
                  ))}
                </div>

                {/* Reasoning accordion for assistant messages with reasoning */}
                {msg.role === "assistant" && msg.reasoningParts && msg.reasoningParts.length > 0 && (
                  <div className="mt-3 border-t border-border/30 pt-2">
                    <ChatReasoning
                      partsInAccordion={msg.reasoningParts}
                      defaultValue="reasoning"
                      renderMessagePart={renderMessagePart}
                      className="!border-b-0 !border-transparent"
                    />
                  </div>
                )}
              </div>
              {msg.role === "user" && (
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent text-background">
                  <User className="h-4 w-4" />
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* AI attribution */}
      <div className="mb-2 flex items-center gap-2 text-xs text-text-tertiary">
        <Shield className="h-3 w-3" />
        <span>
          Reasoning is evidence-sourced. Every numeric comparison is
          deterministic — the AI suggests, you decide.
        </span>
      </div>

      {/* Chat input */}
      <div className="mt-2">
        <AdvancedChatInput
          textareaProps={{
            value: inputValue,
            onChange: (e) => setInputValue(e.target.value),
            placeholder:
              "Ask about a requirement, evidence, or compliance status…",
            onKeyDown: (e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            },
          }}
          sendButtonProps={{
            onClick: handleSend,
          }}
          files={files}
          onFileRemove={handleRemoveFile}
          onSend={handleSend}
          actionIcons={actionIcons}
          className="border-border bg-background"
        />
      </div>
    </div>
  );
}
