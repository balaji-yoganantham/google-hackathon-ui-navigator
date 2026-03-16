import { motion } from "framer-motion";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Bot, PlusCircle } from "lucide-react";
import { useAgentStore } from "@/store/agentStore";

export type MainTab = "planner" | "executor" | "history";

const TABS: { id: MainTab; label: string }[] = [
  { id: "planner", label: "Planner" },
  { id: "executor", label: "Executor Agents" },
  { id: "history", label: "History" },
];

interface DashboardHeaderProps {
  activeTab: MainTab;
  onTabChange: (tab: MainTab) => void;
}

export function DashboardHeader({ activeTab, onTabChange }: DashboardHeaderProps) {
  const { reset } = useAgentStore();

  const handleNewTask = () => {
    reset();
  };

  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="glass-header h-16 flex items-center justify-between px-6 shrink-0 z-50 bg-background"
    >
      <div className="flex items-center gap-8">
        <div className="flex items-center gap-2.5">
          <Bot className="h-7 w-7 text-primary" />
          <span className="text-base font-semibold text-foreground tracking-tight">
            UI Navigator
          </span>
        </div>

        <nav className="flex items-center rounded-lg bg-muted/60 p-0.5" role="tablist">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? "text-foreground bg-background shadow-sm border border-border"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <Button
          size="sm"
          className="gap-2 bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm"
          onClick={handleNewTask}
          title="Start a new task (new session)"
        >
          <PlusCircle className="h-4 w-4" />
          New Task
        </Button>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Avatar className="h-8 w-8 border border-border cursor-pointer">
                <AvatarFallback className="text-xs font-medium bg-muted text-muted-foreground">
                  U
                </AvatarFallback>
              </Avatar>
            </TooltipTrigger>
            <TooltipContent side="bottom">User</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </motion.header>
  );
}
