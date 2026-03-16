import { DashboardHeader } from "@/components/DashboardHeader";
import { AgentVision } from "@/components/AgentVision";
import { TaskDock } from "@/components/TaskDock";
import { LogsPanel } from "@/components/LogsPanel";
import { StatusBanner } from "@/components/StatusBanner";

const Index = () => {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <DashboardHeader />
      <div className="flex flex-1 min-h-0">
        {/* Left: browser view only */}
        <div className="flex-1 flex flex-col min-w-0">
          <AgentVision />
        </div>
        {/* Right panel: task description, controls, answer, then steps/history */}
        <div className="w-80 shrink-0 flex flex-col border-l border-border bg-card/50 min-h-0 overflow-hidden">
          <div className="shrink-0 overflow-y-auto">
            <TaskDock />
          </div>
          <div className="flex-1 min-h-0 flex flex-col border-t border-border">
            <LogsPanel />
          </div>
        </div>
      </div>
      <StatusBanner />
    </div>
  );
};

export default Index;
