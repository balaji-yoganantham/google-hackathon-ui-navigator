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
        {/* Left + Center */}
        <div className="flex-1 flex flex-col min-w-0">
          <AgentVision />
          <TaskDock />
        </div>
        {/* Right panel */}
        <LogsPanel />
      </div>
      <StatusBanner />
    </div>
  );
};

export default Index;
