import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import {
  MousePointer,
  Type,
  ArrowDown,
  Navigation,
  Timer,
  FileSearch,
  CheckCircle2,
  XCircle,
  Clock,
} from "lucide-react";
import type { ExecutionStep } from "@/store/agentStore";

const actionIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  click: MousePointer,
  type: Type,
  scroll: ArrowDown,
  navigate: Navigation,
  wait: Timer,
  extract: FileSearch,
};

const actionColors: Record<string, string> = {
  click: "bg-primary/20 text-primary border-primary/30",
  type: "bg-amber-500/20 text-amber-500 border-amber-500/30",
  scroll: "bg-cyan-500/20 text-cyan-600 border-cyan-500/30",
  navigate: "bg-emerald-500/20 text-emerald-600 border-emerald-500/30",
  wait: "bg-muted text-muted-foreground border-border",
  extract: "bg-purple-500/20 text-purple-600 border-purple-500/30",
};

interface ExecutionTimelineProps {
  steps: ExecutionStep[];
  onSelectScreenshot?: (url: string) => void;
}

export function ExecutionTimeline({ steps, onSelectScreenshot }: ExecutionTimelineProps) {
  if (steps.length === 0) return null;

  return (
    <div className="space-y-0">
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
        Steps
      </div>
      <ul className="relative space-y-3">
        {steps.map((step, index) => {
          const Icon = actionIcons[step.actionType] || MousePointer;
          const colorClass = actionColors[step.actionType] || actionColors.click;
          return (
            <AnimatePresence key={step.stepNumber}>
              <motion.li
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2, delay: index * 0.05 }}
                className="relative flex gap-3"
              >
                <div className="flex flex-col items-center shrink-0">
                  <div
                    className={`rounded-full p-1.5 border ${colorClass}`}
                  >
                    <Icon className="h-3 w-3" />
                  </div>
                  {index < steps.length - 1 && (
                    <div className="w-px flex-1 min-h-[8px] bg-border mt-1" />
                  )}
                </div>
                <div className="flex-1 min-w-0 pb-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge
                      variant="outline"
                      className={`text-[10px] gap-1 px-1.5 py-0 h-5 ${colorClass}`}
                    >
                      <Icon className="h-2.5 w-2.5" />
                      {step.actionType}
                    </Badge>
                    {step.result === "success" && (
                      <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                    )}
                    {step.result === "fail" && (
                      <XCircle className="h-3.5 w-3.5 text-destructive" />
                    )}
                    {step.result === "pending" && (
                      <Clock className="h-3.5 w-3.5 text-muted-foreground animate-pulse" />
                    )}
                  </div>
                  <p className="text-xs text-foreground/90 mt-1 leading-relaxed">
                    {step.reasoning}
                  </p>
                  {(step.screenshotUrl || step.beforeScreenshotUrl) && onSelectScreenshot && (
                    <div className="flex gap-2 mt-2">
                      {step.screenshotUrl && (
                        <button
                          type="button"
                          onClick={() => onSelectScreenshot(step.screenshotUrl!)}
                          className="text-[10px] text-primary hover:underline"
                        >
                          View screenshot
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </motion.li>
            </AnimatePresence>
          );
        })}
      </ul>
    </div>
  );
}
