"use client";

import * as React from "react";
import {
  AdvancedChatInput,
  type FileAttachment,
} from "@/components/ui/advanced-ai-chat-input";
import { Button } from "@/components/ui/button";
import { FileText, Link, Mic, Plus } from "lucide-react";

export default function AdvancedChatInputDemo() {
  const [inputValue, setInputValue] = React.useState("");
  const [files, setFiles] = React.useState<FileAttachment[]>([]);

  // Handler to add a new file attachment
  const handleAddFile = () => {
    const newFile: FileAttachment = {
      id: Date.now(),
      name: `document_${files.length + 1}.pdf`,
      icon: <FileText className="h-4 w-4 text-muted-foreground" />,
    };
    setFiles((prevFiles) => [...prevFiles, newFile]);
  };

  // Handler to remove a file by its ID
  const handleRemoveFile = (id: string | number) => {
    setFiles((prevFiles) => prevFiles.filter((file) => file.id !== id));
  };

  // Handler for the send action
  const handleSend = () => {
    if (!inputValue && files.length === 0) return;
    console.log("Sending:", {
      message: inputValue,
      files: files.map((f) => f.name),
    });
    // Reset state after sending
    setInputValue("");
    setFiles([]);
  };

  // Define action icons to be passed as a prop
  const actionIcons = [
    <Button key="link" variant="ghost" size="icon" aria-label="Attach link">
      <Link className="h-4 w-4 text-muted-foreground" />
    </Button>,
    <Button key="mic" variant="ghost" size="icon" aria-label="Use microphone">
      <Mic className="h-4 w-4 text-muted-foreground" />
    </Button>,
  ];

  return (
    <div className="flex min-h-[400px] w-full flex-col items-center justify-center gap-4 bg-background p-4">
      <div className="w-full max-w-lg">
        <AdvancedChatInput
          textareaProps={{
            value: inputValue,
            onChange: (e) => setInputValue(e.target.value),
            placeholder: "What's on your mind?",
            onKeyDown: (e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            },
          }}
          files={files}
          onFileRemove={handleRemoveFile}
          onSend={handleSend}
          actionIcons={actionIcons}
        />
      </div>

      {/* Demo control to add files dynamically */}
      <Button variant="outline" onClick={handleAddFile}>
        <Plus className="mr-2 h-4 w-4" />
        Attach a file
      </Button>
    </div>
  );
}
