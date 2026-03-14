import { Globe } from "lucide-react";
import { useAgentStore } from "@/store/agentStore";
import { Badge } from "@/components/ui/badge";
import { toDataUrl } from "@/lib/api";

export function AgentVision() {
  const { task } = useAgentStore();
  const isRunning = task?.status === 'running' || task?.status === 'pending';

  // currentScreenshot may be raw base64 or already a data-URL — normalise both
  const rawScreenshot = task?.currentScreenshot ?? '';
  const screenshot = rawScreenshot ? toDataUrl(rawScreenshot) : '';

  return (
    <div className="flex-1 flex flex-col min-w-0 p-4 pb-0">
      <div className="relative flex-1 rounded-lg glow-border bg-card overflow-hidden">
        {/* Live badge */}
        {isRunning && (
          <div className="absolute top-3 right-3 z-10">
            <Badge className="bg-success/20 text-success border-success/30 gap-1.5 text-xs font-mono">
              <span className="h-2 w-2 rounded-full bg-success pulse-live inline-block" />
              Live
            </Badge>
          </div>
        )}

        {screenshot ? (
          <img
            src={screenshot}
            alt="Agent browser view"
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-muted-foreground">
            <div className="p-4 rounded-full bg-secondary">
              <Globe className="h-10 w-10" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-foreground">Enter a URL and task to begin</p>
              <p className="text-xs mt-1 text-muted-foreground">
                The agent will navigate and execute your instructions
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
