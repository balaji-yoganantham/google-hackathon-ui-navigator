import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentStore, ExecutionStep, AgentTask } from "@/store/agentStore";
import {
  CheckCircle2, XCircle, Clock, MousePointer, Type, ArrowDown,
  Navigation, Timer, FileSearch, ChevronDown, ChevronRight, Play,
  Circle, Keyboard,
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
  hover: MousePointer,
  press: Keyboard,
  screenshot: FileSearch,
};

const actionColors: Record<string, string> = {
  click: 'bg-primary/20 text-primary border-primary/30',
  type: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  scroll: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  navigate: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  wait: 'bg-muted text-muted-foreground border-border',
  extract: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
};

// ── ActivityFeed (live plan + phase) ──────────────────────────────────────────

function ActivityFeed({ task }: { task: AgentTask }) {
  const node = task.currentNode ?? '';
  const planDecisions = task.planDecisions ?? [];
  const currentIdx = task.currentDecisionIndex ?? 0;
  const total = planDecisions.length;

  const displayStep = total > 0 ? Math.min(currentIdx + 1, total) : 0;
  const completingStep = node === 'execute_step' && total > 0 && currentIdx >= total;
  const phaseLabel =
    node === 'navigate'
      ? 'Navigating'
      : node === 'plan'
        ? 'Planning (taking screenshot…)'
        : node === 'verify'
          ? 'Verifying progress…'
          : node === 'execute_step' && total > 0
            ? completingStep
              ? `Completing step ${total} of ${total}`
              : `Executing step ${displayStep} of ${total}`
            : node === 'execute_step'
              ? 'Executing'
              : 'Running';

  const showPlan = planDecisions.length > 0 || (task.planSummary ?? '').length > 0;

  return (
    <div className="space-y-2 mb-3">
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="text-[10px] gap-1 px-2 py-0.5 h-6 bg-primary/10 text-primary border-primary/30">
          <Play className="h-3 w-3 animate-pulse" />
          {phaseLabel}
        </Badge>
      </div>
      {showPlan && (
        <>
          {task.planSummary && (
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              Plan: {task.planSummary}
            </p>
          )}
          {planDecisions.length > 0 && (
            <div className="rounded-md bg-secondary/30 border border-border p-2 space-y-1.5">
              {planDecisions.map((d, i) => {
                const Icon = actionIcons[d.actionType] || MousePointer;
                const done = i < currentIdx;
                const current = i === currentIdx;
                return (
                  <div
                    key={i}
                    className={`flex items-start gap-2 text-[11px] ${current ? 'text-primary' : done ? 'text-muted-foreground' : 'text-muted-foreground/80'}`}
                  >
                    <span className="shrink-0 mt-0.5">
                      {done && <CheckCircle2 className="h-3.5 w-3.5 text-success" />}
                      {current && <Play className="h-3.5 w-3.5 text-primary animate-pulse" />}
                      {!done && !current && <Circle className="h-3.5 w-3.5" />}
                    </span>
                    <span className="font-mono text-[10px] shrink-0">
                      {i + 1}. [{d.actionType}]
                    </span>
                    <span className="flex-1 min-w-0 leading-relaxed">{d.reasoning}</span>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Comet-style sub-step label from action ───────────────────────────────────

function getActionSubLabel(step: ExecutionStep): { icon: any; label: string } {
  const Icon = actionIcons[step.actionType] || MousePointer;
  const payload = step.actionPayload;
  if (step.actionType === 'type' && payload?.text != null) {
    return { icon: Type, label: `Typing: ${payload.text}` };
  }
  if (step.actionType === 'click') {
    return { icon: MousePointer, label: 'Clicking' };
  }
  if (step.actionType === 'press' && payload?.key != null) {
    return { icon: Keyboard, label: `Pressing key: ${payload.key}` };
  }
  if (step.actionType === 'scroll') {
    return { icon: ArrowDown, label: 'Scrolling' };
  }
  if (step.actionType === 'navigate' && payload?.url != null) {
    return { icon: Navigation, label: `Navigating: ${payload.url}` };
  }
  if (step.actionType === 'hover') {
    return { icon: MousePointer, label: 'Hovering' };
  }
  return { icon: Icon, label: step.actionType };
}

// ── StepCard (Comet-style) ───────────────────────────────────────────────────

function StepCard({ step, onSelect }: { step: ExecutionStep; onSelect?: (url: string) => void }) {
  const [showAction, setShowAction] = useState(false);
  const { icon: SubIcon, label: subLabel } = getActionSubLabel(step);
  const hasPayload = step.actionPayload && Object.keys(step.actionPayload).length > 0;
  const oneLineLabel = step.reasoning?.trim() || subLabel;

  return (
    <div
        className={`slide-in flex-1 min-w-0 rounded-md bg-secondary/50 border border-border p-3 space-y-2 ${step.screenshotUrl ? 'cursor-pointer hover:border-primary/50 transition-colors' : ''}`}
        onClick={(e) => { if (step.screenshotUrl && !(e.target as HTMLElement).closest('button')) onSelect?.(step.screenshotUrl); }}
      >
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-[10px] px-1.5 py-0 h-5 min-w-[28px] justify-center">
            {step.stepNumber}
          </Badge>
          <span className="text-xs font-medium text-foreground truncate flex-1">{oneLineLabel}</span>
          {step.result === 'success' && <CheckCircle2 className="h-3.5 w-3.5 text-success shrink-0" />}
          {step.result === 'fail' && <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" />}
          {step.result === 'pending' && <Clock className="h-3.5 w-3.5 text-muted-foreground animate-pulse shrink-0" />}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <SubIcon className="h-3 w-3 shrink-0" />
          <span>{subLabel}</span>
        </div>
        {step.screenshotUrl && (
          <div className="relative rounded border border-border overflow-hidden">
            <img
              src={step.screenshotUrl}
              alt={`Step ${step.stepNumber}`}
              className="w-full max-h-40 object-contain object-top bg-muted/30"
            />
            <div className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity bg-black/40">
              <span className="text-[10px] text-white font-medium">Click to expand</span>
            </div>
          </div>
        )}
        {hasPayload && (
          <div className="pt-1 border-t border-border/50">
            <button
              type="button"
              className="text-[10px] font-medium text-muted-foreground hover:text-foreground"
              onClick={(e) => { e.stopPropagation(); setShowAction((v) => !v); }}
            >
              {showAction ? 'Hide action' : 'Show action'}
            </button>
            {showAction && (
              <pre className="mt-1.5 p-2 rounded bg-muted/50 text-[10px] font-mono overflow-x-auto whitespace-pre-wrap break-all">
                {JSON.stringify(step.actionPayload, null, 2)}
              </pre>
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
  const [stepsExpanded, setStepsExpanded] = useState(true);
  const steps = activeTab === 'current' ? (task?.steps || []) : [];
  const showSkeleton = isLoading && steps.length === 0;
  const completed = task?.status === 'completed' && steps.length > 0;
  const truncateDesc = (s: string, max: number) =>
    s.length <= max ? s : s.slice(0, max).trim() + '…';

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
            {task && <ActivityFeed task={task} />}
            {showSkeleton && (
              <>
                <StepSkeleton />
                <StepSkeleton />
                <StepSkeleton />
              </>
            )}
            {steps.length > 0 && (
              <>
                <button
                  type="button"
                  className="flex items-center gap-2 w-full text-left text-[10px] font-medium text-muted-foreground uppercase tracking-wide hover:text-foreground py-1.5"
                  onClick={() => setStepsExpanded((v) => !v)}
                >
                  {stepsExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                  )}
                  {steps.length} step{steps.length !== 1 ? 's' : ''} completed
                </button>
                {stepsExpanded && (
                  <div className="flex gap-3">
                    <div className="flex flex-col items-center shrink-0 pt-0.5">
                      {steps.map((_, i) => (
                        <div key={i} className="flex flex-col items-center">
                          <div className="w-2.5 h-2.5 rounded-full bg-primary/80 shrink-0" />
                          {i < steps.length - 1 && (
                            <div className="w-px min-h-4 bg-border my-0.5" />
                          )}
                        </div>
                      ))}
                    </div>
                    <div className="flex-1 min-w-0 space-y-2 pb-2">
                      {steps.map((step) => (
                        <StepCard
                          key={step.stepNumber}
                          step={step}
                          onSelect={(url) => setSelectedStepScreenshot(url)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
            {completed && (
              <div className="rounded-md bg-success/10 border border-success/30 px-3 py-2 mt-2">
                <p className="text-xs font-medium text-success">Task completed.</p>
                {task.taskDescription && (
                  <p className="text-[11px] text-muted-foreground mt-1 truncate" title={task.taskDescription}>
                    {truncateDesc(task.taskDescription, 80)}
                  </p>
                )}
              </div>
            )}
            {!isLoading && steps.length === 0 && !task && (
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
