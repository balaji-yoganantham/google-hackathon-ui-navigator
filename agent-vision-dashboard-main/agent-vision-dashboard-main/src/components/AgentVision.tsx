import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, Globe } from "lucide-react";
import { useAgentStore } from "@/store/agentStore";
import { Badge } from "@/components/ui/badge";
import { toDataUrl } from "@/lib/api";
import { useBrowserStream } from "@/hooks/use-browser-stream";

function formatElapsed(startedAt: string | undefined): string {
  if (!startedAt) return "0:00";
  const start = new Date(startedAt).getTime();
  const sec = Math.floor((Date.now() - start) / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function AgentVision() {
  const { task, selectedStepScreenshot, setSelectedStepScreenshot } = useAgentStore();
  const isRunning = task?.status === 'running' || task?.status === 'pending';
  const [elapsed, setElapsed] = useState(() => formatElapsed(task?.startedAt));

  // Update elapsed every second when running
  useEffect(() => {
    if (!isRunning) return;
    setElapsed(formatElapsed(task?.startedAt));
    const t = setInterval(() => setElapsed(formatElapsed(task?.startedAt)), 1000);
    return () => clearInterval(t);
  }, [isRunning, task?.startedAt]);

  // WebSocket live feed — high-frequency frames pushed by the backend after every action
  const { screenshot: wsScreenshot, connected: wsConnected } = useBrowserStream(
    task?.sessionId ?? null,
    isRunning,
  );

  // Priority: pinned step > WebSocket live frame > SSE-embedded screenshot
  const sseFallback = task?.currentScreenshot ? toDataUrl(task.currentScreenshot) : '';
  const liveScreenshot = wsScreenshot || sseFallback;
  const displayScreenshot = selectedStepScreenshot || liveScreenshot;

  // Prominent "Agent running" screen when task just started (no screenshot yet) — like recording UI
  const showRunningState = isRunning && !displayScreenshot;

  return (
    <motion.div
      className="flex-1 flex flex-col min-w-0 p-4 pb-0"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <div className="relative flex-1 rounded-xl glow-border bg-card overflow-hidden border border-border shadow-sm">

        {/* Full-screen "Agent running" state when task started and no frame yet */}
        {showRunningState && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-6 bg-black rounded-lg">
            <div className="relative flex items-center justify-center">
              <div className="absolute inset-0 rounded-full bg-emerald-500/20 border-2 border-emerald-400/50 animate-ping scale-150" style={{ animationDuration: '1.5s' }} />
              <div className="relative rounded-full bg-emerald-500/10 border-2 border-emerald-400 p-6">
                <Activity className="h-12 w-12 text-emerald-400" />
              </div>
            </div>
            <div className="text-center space-y-1">
              <p className="text-lg font-medium text-white tabular-nums">
                Running... {elapsed}
              </p>
              <p className="text-sm text-white/70">
                The agent is navigating and executing your task
              </p>
            </div>
          </div>
        )}

        {/* Live badge — only when no step is pinned */}
        {isRunning && !selectedStepScreenshot && (
          <div className="absolute top-3 right-3 z-10 flex flex-col items-end gap-1">
            <Badge className="bg-success/20 text-success border-success/30 gap-1.5 text-xs font-mono">
              <span className="h-2 w-2 rounded-full bg-success pulse-live inline-block" />
              Live
            </Badge>
            {task?.startUrl && (
              <span className="text-[10px] font-mono text-muted-foreground max-w-[200px] truncate" title={task.startUrl}>
                {task.startUrl}
              </span>
            )}
          </div>
        )}

        {displayScreenshot ? (
          <img
            src={displayScreenshot}
            alt="Agent browser view"
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full min-h-[60vh] w-full py-16 gap-8 text-muted-foreground">
            <div className="p-8 rounded-full bg-secondary/80">
              <Globe className="h-20 w-20" />
            </div>
            <div className="text-center space-y-2 max-w-md">
              <p className="text-lg font-medium text-foreground">Enter a URL and task to begin</p>
              <p className="text-sm text-muted-foreground">
                The agent will navigate and execute your instructions
              </p>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
