"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Bot, FileText, MessageCircle, Send, X } from "lucide-react";

import { AdvancedChatInput, type FileAttachment } from "@/components/ui/advanced-ai-chat-input";

interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  content: string;
  timestamp: Date;
}

const initialMessages: ChatMessage[] = [
  {
    id: "1",
    role: "assistant",
    content:
      "Hello! I'm your Tender Compliance AI assistant. I can help you understand requirements, find evidence, and navigate the compliance matrix. What would you like to explore?",
    timestamp: new Date(),
  },
];

const actionIconsData = [
  { icon: <FileText className="h-4 w-4" />, label: "Attach document" },
  { icon: <Send className="h-4 w-4" />, label: "Send" },
];

export function AIAssistantPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [files, setFiles] = useState<FileAttachment[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!inputValue && files.length === 0) return;

    const newUserMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, newUserMessage]);

    // Simulate AI response
    const timer = setTimeout(() => {
      const aiResponse: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content:
          "Based on the current compliance matrix, I've identified 3 requirements that need your review. Would you like me to walk through them?",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiResponse]);
    }, 800);

    setInputValue("");
    setFiles([]);
    return () => clearTimeout(timer);
  };

  const handleRemoveFile = (id: string | number) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  // Action icons for the chat input
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
      key="mic"
      className="flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary hover:bg-surface-elevated hover:text-text-primary"
      aria-label="Voice input"
      type="button"
    >
      <svg
        className="h-4 w-4"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    </button>,
  ];

  return (
    <>
      {/* Floating toggle button */}
      <AnimatePresence>
        {!isOpen && (
          <motion.button
            className={cn(
              "fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full",
              "bg-accent px-4 py-3 text-sm font-medium text-background shadow-lg",
              "hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent",
            )}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            onClick={() => setIsOpen(true)}
            whileHover={{ scale: 1.05 }}
          >
            <MessageCircle className="h-5 w-5" />
            <span>AI Assistant</span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Chat panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className={cn(
              "fixed inset-y-6 right-6 z-40 flex h-[calc(100vh-48px)] w-80",
              "flex-col rounded-2xl border border-border bg-surface shadow-2xl",
            )}
            initial={{ x: "100%", opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
          >
            {/* Header */}
            <div className="flex h-14 items-center justify-between border-b border-border px-4">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/10">
                  <Bot className="h-4 w-4 text-accent" />
                </div>
                <span className="font-medium text-text-primary">
                  Compliance Assistant
                </span>
              </div>
              <button
                className="rounded-lg p-1 text-text-tertiary hover:bg-surface-elevated hover:text-text-primary"
                onClick={() => setIsOpen(false)}
                aria-label="Close assistant"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Messages */}
            <div
              ref={messagesEndRef}
              className="flex-1 overflow-y-auto p-4"
            >
              <div className="space-y-4">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      "flex gap-2.5",
                      msg.role === "user"
                        ? "justify-end"
                        : "justify-start",
                    )}
                  >
                    {msg.role === "assistant" && (
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                        <Bot className="h-3 w-3" />
                      </div>
                    )}
                    <div
                      className={cn(
                        "max-w-[80%] rounded-xl px-3 py-2 text-sm",
                        msg.role === "user"
                          ? "bg-accent text-background"
                          : "bg-background text-text-secondary",
                      )}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Chat input */}
            <div className="border-t border-border p-3">
              <AdvancedChatInput
                textareaProps={{
                  value: inputValue,
                  onChange: (e) => setInputValue(e.target.value),
                  placeholder: "Ask about requirements or evidence…",
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
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
