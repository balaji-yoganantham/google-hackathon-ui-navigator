import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Play } from "lucide-react";
import { useAgentStore } from "@/store/agentStore";

interface PlannerCardProps {
  onStartTask?: () => void;
}

export function PlannerCard({ onStartTask }: PlannerCardProps) {
  const { taskDescription, setTaskDescription, isLoading, setTriggerSend } = useAgentStore();

  const handleStartTask = () => {
    if (!taskDescription.trim() || isLoading) return;
    setTriggerSend(true);
    onStartTask?.();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="p-6 max-w-2xl mx-auto"
    >
      <Card className="card-modern overflow-hidden shadow-sm border-border">
        <CardHeader className="space-y-1 pb-4">
          <CardTitle className="text-lg font-semibold text-foreground">
            New task
          </CardTitle>
          <CardDescription className="text-sm text-muted-foreground">
            Describe what you want the agent to do. You can optionally set a start URL.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="planner-url" className="text-sm font-medium text-foreground">
              Start URL <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Input
              id="planner-url"
              placeholder="https://www.google.com"
              className="input-modern w-full"
              disabled={isLoading}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="planner-task" className="text-sm font-medium text-foreground">
              Task description
            </Label>
            <Textarea
              id="planner-task"
              placeholder="Describe what you want the agent to do..."
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              className="input-modern min-h-[120px] resize-none w-full"
              disabled={isLoading}
              rows={4}
            />
          </div>
          <Button
            onClick={handleStartTask}
            disabled={!taskDescription.trim() || isLoading}
            className="w-full gap-2 bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm"
          >
            <Play className="h-4 w-4" />
            {isLoading ? "Running…" : "Start Task"}
          </Button>
        </CardContent>
      </Card>
    </motion.div>
  );
}
