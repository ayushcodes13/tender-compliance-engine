import { ProjectsGrid } from "@/components/dashboard/projects-grid";
import { AIAssistantPanel } from "@/components/dashboard/ai-assistant-panel";

export default function DashboardPage() {
  return (
    <>
      <ProjectsGrid />
      <AIAssistantPanel />
    </>
  );
}
