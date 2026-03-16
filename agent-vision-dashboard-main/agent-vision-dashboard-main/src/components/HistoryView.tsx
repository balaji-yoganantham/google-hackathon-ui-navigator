import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Play, ChevronRight } from "lucide-react";
import { useAgentStore, type AgentTask } from "@/store/agentStore";

function HistoryCard({ task, index, onContinue }: { task: AgentTask; index: number; onContinue?: () => void }) {
  const { startContinue, setActiveTab } = useAgentStore();

  const statusColor =
    task.status === "completed"
      ? "bg-success/20 text-success border-success/30"
      : task.status === "failed"
        ? "bg-destructive/20 text-destructive border-destructive/30"
        : "bg-muted text-muted-foreground border-border";

  const handleContinue = () => {
    startContinue(task);
    setActiveTab("logs");
    onContinue?.();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
    >
      <Card className="card-modern overflow-hidden hover:shadow-md transition-shadow">
        <CardContent className="p-4 flex items-center gap-4">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground truncate">
              {task.taskDescription || "Untitled task"}
            </p>
            {task.startUrl && (
              <p className="text-xs text-muted-foreground truncate mt-0.5">
                {task.startUrl}
              </p>
            )}
            <div className="flex items-center gap-2 mt-2">
              <Badge variant="outline" className="text-[10px] font-mono">
                {task.steps?.length ?? 0} steps
              </Badge>
              <Badge className={`text-[10px] ${statusColor}`}>{task.status}</Badge>
            </div>
          </div>
          {(task.status === "completed" || task.status === "failed") && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 shrink-0"
              onClick={handleContinue}
            >
              <Play className="h-3 w-3" />
              Continue
            </Button>
          )}
          <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
        </CardContent>
      </Card>
    </motion.div>
  );
}

interface HistoryViewProps {
  onContinue?: () => void;
}

export function HistoryView({ onContinue }: HistoryViewProps) {
  const { history } = useAgentStore();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="p-6 max-w-2xl mx-auto"
    >
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-4">
        Past tasks
      </div>
      {history.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No past tasks yet. Start a task from the Planner tab.
        </p>
      ) : (
        <ul className="space-y-3">
          <AnimatePresence mode="popLayout">
            {history.map((task, index) => (
              <li key={task.sessionId || index}>
                <HistoryCard task={task} index={index} onContinue={onContinue} />
              </li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </motion.div>
  );
}
