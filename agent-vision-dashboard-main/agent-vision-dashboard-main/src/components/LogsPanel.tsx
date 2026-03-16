import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentStore, ExecutionStep, AgentTask } from "@/store/agentStore";
import {
  CheckCircle2, XCircle, Clock, MousePointer, Type, ArrowDown,
  Navigation, Timer, FileSearch, ChevronDown, ChevronRight, Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ── Action metadata ──────────────────────────────────────────────────────────

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

// ── StepCard ─────────────────────────────────────────────────────────────────

function StepCard({ step, onSelect }: { step: ExecutionStep; onSelect?: (url: string) => void }) {
  const Icon = actionIcons[step.actionType] || MousePointer;
  const hasBefore = !!step.beforeScreenshotUrl;
  const hasAfter = !!step.screenshotUrl;
  const hasAnyScreenshot = hasBefore || hasAfter;

  return (
    <div
      className={`slide-in rounded-md bg-secondary/50 border border-border p-3 space-y-2 ${hasAnyScreenshot ? 'cursor-pointer hover:border-primary/50 transition-colors' : ''}`}
      onClick={() => (step.screenshotUrl && onSelect?.(step.screenshotUrl)) || (step.beforeScreenshotUrl && onSelect?.(step.beforeScreenshotUrl))}
    >
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
      {(hasBefore || hasAfter) && (
        <div className="grid grid-cols-2 gap-1.5">
          {hasBefore && (
            <div className="relative" onClick={(e) => { e.stopPropagation(); onSelect?.(step.beforeScreenshotUrl!); }}>
              <img
                src={step.beforeScreenshotUrl}
                alt={`Step ${step.stepNumber} before`}
                className="w-full h-14 object-cover rounded border border-border"
              />
              <div className="absolute bottom-0 left-0 right-0 bg-black/60 rounded-b text-[9px] text-center text-white py-0.5">Before</div>
            </div>
          )}
          {hasAfter && (
            <div className="relative" onClick={(e) => { e.stopPropagation(); onSelect?.(step.screenshotUrl!); }}>
              <img
                src={step.screenshotUrl}
                alt={`Step ${step.stepNumber} after`}
                className="w-full h-14 object-cover rounded border border-border"
              />
              <div className="absolute bottom-0 left-0 right-0 bg-black/60 rounded-b text-[9px] text-center text-white py-0.5">After</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── StepSkeleton ─────────────────────────────────────────────────────────────

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

// ── HistoryTaskCard ───────────────────────────────────────────────────────────

function HistoryTaskCard({ task }: { task: AgentTask }) {
  const [expanded, setExpanded] = useState(false);
  const { setSelectedStepScreenshot, startContinue, setActiveTab } = useAgentStore();

  const statusColor =
    task.status === 'completed' ? 'bg-success/20 text-success border-success/30' :
    task.status === 'failed' ? 'bg-destructive/20 text-destructive border-destructive/30' :
    'bg-muted text-muted-foreground border-border';

  const handleContinue = () => {
    startContinue(task);
    setActiveTab('current');
  };

  return (
    <div className="rounded-md bg-secondary/50 border border-border overflow-hidden">
      {/* Header row */}
      <div
        className="flex items-center gap-2 p-3 cursor-pointer hover:bg-secondary/80 transition-colors select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded
          ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-foreground truncate">{task.taskDescription}</p>
          {task.startUrl && (
            <p className="text-[10px] font-mono text-muted-foreground truncate mt-0.5">{task.startUrl}</p>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge variant="outline" className="text-[9px] font-mono px-1 py-0 h-4">
            {task.steps.length}
          </Badge>
          <Badge className={`text-[9px] px-1.5 py-0 h-4 ${statusColor}`}>
            {task.status}
          </Badge>
        </div>
      </div>

      {/* Expanded: steps + continue button */}
      {expanded && (
        <div className="border-t border-border">
          {/* Continue button */}
          {(task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') && (
            <div className="px-3 py-2 border-b border-border">
              <Button
                size="sm"
                variant="outline"
                className="w-full gap-1.5 text-xs h-7"
                onClick={handleContinue}
              >
                <Play className="h-3 w-3" />
                Continue from this session
              </Button>
            </div>
          )}

          {/* Step list */}
          <div className="p-3 space-y-2">
            {task.steps.length === 0 ? (
              <p className="text-[11px] text-muted-foreground text-center py-2">No steps recorded</p>
            ) : (
              task.steps.map((step) => (
                <StepCard
                  key={step.stepNumber}
                  step={step}
                  onSelect={(url) => setSelectedStepScreenshot(url)}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── LogsPanel ─────────────────────────────────────────────────────────────────

export function LogsPanel() {
  const { task, isLoading, activeTab, setActiveTab, history, setSelectedStepScreenshot } = useAgentStore();
  const steps = activeTab === 'current' ? (task?.steps || []) : [];
  const showSkeleton = isLoading && steps.length === 0;

  return (
    <div className="w-full min-w-0 flex flex-col flex-1 min-h-0 bg-card/50">
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
            {tab === 'history' && history.length > 0 && (
              <Badge variant="outline" className="ml-1.5 text-[9px] px-1 py-0 h-4">
                {history.length}
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
              <StepCard
                key={step.stepNumber}
                step={step}
                onSelect={(url) => setSelectedStepScreenshot(url)}
              />
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
                <p className="text-xs text-muted-foreground">No history yet</p>
              </div>
            ) : (
              history.map((t, i) => (
                <HistoryTaskCard key={t.sessionId || i} task={t} />
              ))
            )}
          </>
        )}
      </div>
    </div>
  );
}
