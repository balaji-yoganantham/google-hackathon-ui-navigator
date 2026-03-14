import { Globe, Radio } from "lucide-react";
import { useAgentStore } from "@/store/agentStore";
import { Badge } from "@/components/ui/badge";
import { toDataUrl } from "@/lib/api";

export function AgentVision() {
  const { task, selectedStepScreenshot, setSelectedStepScreenshot } = useAgentStore();
  const isRunning = task?.status === 'running' || task?.status === 'pending';

  const liveScreenshot = task?.currentScreenshot
    ? toDataUrl(task.currentScreenshot)
    : '';

  // Step screenshot takes priority over live feed
  const displayScreenshot = selectedStepScreenshot || liveScreenshot;

  return (
    <div className="flex-1 flex flex-col min-w-0 p-4 pb-0">
      <div className="relative flex-1 rounded-lg glow-border bg-card overflow-hidden">

        {/* Live badge — only when no step is pinned */}
        {isRunning && !selectedStepScreenshot && (
          <div className="absolute top-3 right-3 z-10">
            <Badge className="bg-success/20 text-success border-success/30 gap-1.5 text-xs font-mono">
              <span className="h-2 w-2 rounded-full bg-success pulse-live inline-block" />
              Live
            </Badge>
          </div>
        )}

        {/* "Back to Live" button when a step screenshot is pinned */}
        {selectedStepScreenshot && (
          <button
            onClick={() => setSelectedStepScreenshot(null)}
            className="absolute top-3 left-3 z-10 flex items-center gap-1.5 rounded-md bg-card/90 border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <Radio className="h-3 w-3 text-success" />
            Back to Live
          </button>
        )}

        {/* Step label badge when pinned */}
        {selectedStepScreenshot && (
          <div className="absolute top-3 right-3 z-10">
            <Badge variant="outline" className="text-[10px] font-mono bg-card/90">
              Step preview
            </Badge>
          </div>
        )}

        {displayScreenshot ? (
          <img
            src={displayScreenshot}
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
