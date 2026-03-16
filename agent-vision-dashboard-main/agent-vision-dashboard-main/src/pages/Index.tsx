import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DashboardHeader, type MainTab } from "@/components/DashboardHeader";
import { AgentVision } from "@/components/AgentVision";
import { TaskDock } from "@/components/TaskDock";
import { LogsPanel } from "@/components/LogsPanel";
import { StatusBanner } from "@/components/StatusBanner";
import { FullReportView } from "@/components/FullReportView";
import { PlannerCard } from "@/components/PlannerCard";
import { HistoryView } from "@/components/HistoryView";
import { QAScanView } from "@/components/QAScanView";
import { useAgentStore } from "@/store/agentStore";

const Index = () => {
  const { task } = useAgentStore();
  const [activeMainTab, setActiveMainTab] = useState<MainTab>("executor");
  const [dismissedReportSessionId, setDismissedReportSessionId] = useState<string | null>(null);
  const hasReports = (task?.reports?.length ?? 0) > 0;
  const showReport = hasReports && task?.sessionId !== dismissedReportSessionId;

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-background">
      <DashboardHeader activeTab={activeMainTab} onTabChange={setActiveMainTab} />
      <div className="flex flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <AnimatePresence mode="wait">
            {showReport ? (
              <FullReportView
                key="report"
                onClose={() => setDismissedReportSessionId(task?.sessionId ?? null)}
              />
            ) : activeMainTab === "planner" ? (
              <PlannerCard key="planner" onStartTask={() => setActiveMainTab("executor")} />
            ) : activeMainTab === "qaScan" ? (
              <QAScanView key="qaScan" onTaskStarted={() => setActiveMainTab("executor")} />
            ) : activeMainTab === "executor" ? (
              <div key="executor" className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
                {(task?.status === "running" || task?.status === "pending") && task?.steps && (
                  <div className="shrink-0 px-4 pt-2 pb-1 flex items-center gap-2">
                    <span className="text-xs font-medium text-muted-foreground">
                      Step {task.steps.length}
                      {(task?.status === "running" || task?.status === "pending") && " (running)"}
                    </span>
                    <div className="flex-1 h-1 rounded-full bg-muted overflow-hidden max-w-[120px]">
                      <div
                        className="h-full bg-primary rounded-full transition-all duration-300"
                        style={{ width: `${Math.min(task.steps.length * 25, 100)}%` }}
                      />
                    </div>
                  </div>
                )}
                <div className="flex-1 min-h-0 p-4 pb-0">
                  <AgentVision />
                </div>
              </div>
            ) : activeMainTab === "history" ? (
              <div key="history" className="flex-1 overflow-y-auto min-h-0">
                <HistoryView onContinue={() => setActiveMainTab("executor")} />
              </div>
            ) : null}
          </AnimatePresence>
        </div>
        <LogsPanel />
      </div>
      <StatusBanner />
      <TaskDock />
    </div>
  );
};

export default Index;
