import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentStore, ExecutionStep } from "@/store/agentStore";
import { CheckCircle2, XCircle, Clock, MousePointer, Type, ArrowDown, Navigation, Timer, FileSearch } from "lucide-react";

const actionIcons: Record<string, any> = {
  click: MousePointer,
  type: Type,
  scroll: ArrowDown,
  navigate: Navigation,
  wait: Timer,
  extract: FileSearch,
};

const actionColors: Record<string, string> = {
  click: 'bg-primary/20 text-primary border-primary/30',
  type: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  scroll: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  navigate: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  wait: 'bg-muted text-muted-foreground border-border',
  extract: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
};

function StepCard({ step }: { step: ExecutionStep }) {
  const Icon = actionIcons[step.actionType] || MousePointer;

  return (
    <div className="slide-in rounded-md bg-secondary/50 border border-border p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="font-mono text-[10px] px-1.5 py-0 h-5 min-w-[28px] justify-center">
          {step.stepNumber}
        </Badge>
        <Badge className={`text-[10px] gap-1 px-1.5 py-0 h-5 ${actionColors[step.actionType] || actionColors.click}`}>
          <Icon className="h-2.5 w-2.5" />
          {step.actionType}
        </Badge>
        <div className="ml-auto">
          {step.result === 'success' && <CheckCircle2 className="h-3.5 w-3.5 text-success" />}
          {step.result === 'fail' && <XCircle className="h-3.5 w-3.5 text-destructive" />}
          {step.result === 'pending' && <Clock className="h-3.5 w-3.5 text-muted-foreground animate-pulse" />}
        </div>
      </div>
      <p className="text-xs font-mono text-muted-foreground leading-relaxed">{step.reasoning}</p>
      {step.screenshotUrl && (
        <img
          src={step.screenshotUrl}
          alt={`Step ${step.stepNumber}`}
          className="w-full h-16 object-cover rounded border border-border hover:h-32 transition-all duration-150 cursor-pointer"
        />
      )}
    </div>
  );
}

function StepSkeleton() {
  return (
    <div className="rounded-md bg-secondary/50 border border-border p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Skeleton className="h-5 w-7" />
        <Skeleton className="h-5 w-16" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}

export function LogsPanel() {
  const { task, isLoading, activeTab, setActiveTab, history } = useAgentStore();
  const steps = activeTab === 'current' ? (task?.steps || []) : [];
  const showSkeleton = isLoading && steps.length === 0;

  return (
    <div className="w-80 border-l border-border flex flex-col shrink-0 bg-card/50">
      {/* Tab switcher */}
      <div className="flex border-b border-border shrink-0">
        {(['current', 'history'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2.5 text-xs font-medium capitalize transition-colors duration-150 ${
              activeTab === tab
                ? 'text-foreground border-b-2 border-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab}
            {tab === 'current' && task && (
              <Badge variant="outline" className="ml-1.5 text-[9px] px-1 py-0 h-4">
                {task.steps.length}
              </Badge>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {activeTab === 'current' ? (
          <>
            {showSkeleton && (
              <>
                <StepSkeleton />
                <StepSkeleton />
                <StepSkeleton />
              </>
            )}
            {steps.map((step) => (
              <StepCard key={step.stepNumber} step={step} />
            ))}
            {!isLoading && steps.length === 0 && (
              <div className="flex items-center justify-center h-full">
                <p className="text-xs text-muted-foreground">No steps yet</p>
              </div>
            )}
          </>
        ) : (
          <>
            {history.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <p className="text-xs text-muted-foreground">No history</p>
              </div>
            ) : (
              history.map((t, i) => (
                <div key={i} className="rounded-md bg-secondary/50 border border-border p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {t.steps.length} steps
                    </Badge>
                    <Badge className={t.status === 'completed' ? 'bg-success/20 text-success border-success/30 text-[10px]' : 'bg-destructive/20 text-destructive border-destructive/30 text-[10px]'}>
                      {t.status}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{t.taskDescription}</p>
                  <p className="text-[10px] font-mono text-muted-foreground truncate">{t.startUrl}</p>
                </div>
              ))
            )}
          </>
        )}
      </div>
    </div>
  );
}
