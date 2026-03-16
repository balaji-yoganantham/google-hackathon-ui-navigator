import { useState, useMemo, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentStore, ExecutionStep, AgentTask } from "@/store/agentStore";
import {
  CheckCircle2, XCircle, Clock, MousePointer, Type, ArrowDown,
  Navigation, Timer, FileSearch, ChevronDown, ChevronRight, Play,
  Terminal, Info, AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReportCardList } from "@/components/ReportCard";

// ── Citadelle-style log entry (derived from task.steps) ───────────────────────

type LogEntryType = 'action' | 'status' | 'error' | 'info' | 'log';

interface LogEntry {
  id: string;
  timestamp: string;
  type: LogEntryType;
  message: string;
}

function useAgentLogs(task: AgentTask | null, isLoading: boolean): LogEntry[] {
  return useMemo(() => {
    const entries: LogEntry[] = [];
    if (!task) return entries;
    const steps = task.steps || [];
    const ts = (d: Date) => d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    let now = new Date();
    entries.push({ id: 'start', timestamp: ts(now), type: 'status', message: `Starting: ${task.taskDescription || 'Task'}` });
    if (task.startUrl) {
      entries.push({ id: 'nav', timestamp: ts(now), type: 'log', message: `Navigating to: ${task.startUrl}` });
    }
    steps.forEach((step, i) => {
      const stepTs = step.timestamp ? new Date(step.timestamp) : now;
      const actionLabel = step.actionType.toUpperCase();
      entries.push({
        id: `step-${step.stepNumber}-action`,
        timestamp: ts(stepTs),
        type: 'action',
        message: `${actionLabel} – ${step.reasoning || ''}`,
      });
      if (step.result === 'success') {
        entries.push({ id: `step-${step.stepNumber}-ok`, timestamp: ts(stepTs), type: 'status', message: `Step ${step.stepNumber} succeeded` });
      } else if (step.result === 'fail') {
        entries.push({ id: `step-${step.stepNumber}-fail`, timestamp: ts(stepTs), type: 'error', message: `Step ${step.stepNumber} failed` });
      }
    });
    if (task.status === 'completed') {
      entries.push({ id: 'done', timestamp: ts(new Date()), type: 'status', message: 'Completed' });
    } else if (task.status === 'failed') {
      entries.push({ id: 'err', timestamp: ts(new Date()), type: 'error', message: task.error || 'Error' });
    } else if (task.status === 'cancelled') {
      entries.push({ id: 'cancel', timestamp: ts(new Date()), type: 'status', message: 'Cancelled' });
    } else if (isLoading && steps.length > 0) {
      entries.push({ id: 'running', timestamp: ts(new Date()), type: 'status', message: 'Running…' });
    }
    return entries;
  }, [task?.id, task?.status, task?.steps, task?.startUrl, task?.taskDescription, task?.error, isLoading]);
}

function LogIcon({ type }: { type: LogEntryType }) {
  switch (type) {
    case 'action': return <MousePointer className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
    case 'status': return <Info className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
    case 'error': return <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />;
    case 'info': return <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />;
    default: return <Terminal className="w-3.5 h-3.5 text-muted-foreground shrink-0" />;
  }
}

function ActionBadgeLog({ message }: { message: string }) {
  const upper = message.toUpperCase();
  if (upper.startsWith('CLICK')) return <Badge variant="secondary" className="text-xs font-mono gap-1"><MousePointer className="w-3 h-3" />{message}</Badge>;
  if (upper.startsWith('TYPE')) return <Badge variant="secondary" className="text-xs font-mono gap-1"><Type className="w-3 h-3" />{message}</Badge>;
  if (upper.startsWith('SCROLL')) return <Badge variant="secondary" className="text-xs font-mono gap-1"><ArrowDown className="w-3 h-3" />{message}</Badge>;
  if (upper.startsWith('EXTRACT') || upper.startsWith('DONE')) return <Badge variant="default" className="text-xs font-mono gap-1"><CheckCircle2 className="w-3 h-3" />{message}</Badge>;
  if (upper.startsWith('NAVIGATE')) return <Badge variant="secondary" className="text-xs font-mono gap-1"><Navigation className="w-3 h-3" />{message}</Badge>;
  return <Badge variant="secondary" className="text-xs font-mono gap-1"><Terminal className="w-3 h-3" />{message}</Badge>;
}

function LogEntryRow({ entry }: { entry: LogEntry }) {
  const isAction = entry.type === 'action';
  const isError = entry.type === 'error';
  const bubbleBg = isError ? 'bg-destructive/5 border-destructive/20' : isAction ? 'bg-primary/5 border-primary/20' : 'bg-muted/50 border-border';
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex gap-2 py-2 px-3 rounded-lg border ${bubbleBg} text-left`}
    >
      <LogIcon type={entry.type} />
      <div className="min-w-0 flex-1">
        <span className="text-[10px] font-mono text-muted-foreground">{entry.timestamp}</span>
        <div className="mt-0.5">
          {isAction && <ActionBadgeLog message={entry.message} />}
          {!isAction && (
            <span className={isError ? 'text-destructive text-xs' : entry.type === 'info' ? 'text-muted-foreground italic text-xs' : 'text-foreground/90 text-xs'}>
              {entry.message}
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

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
      className={`slide-in rounded-lg bg-background border border-border p-3 space-y-2 shadow-sm ${hasAnyScreenshot ? 'cursor-pointer hover:border-primary/40 hover:shadow transition-colors' : ''}`}
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
    <div className="rounded-lg bg-background border border-border p-3 space-y-2 shadow-sm">
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
    setActiveTab('logs');
  };

  return (
    <div className="rounded-lg bg-background border border-border overflow-hidden shadow-sm">
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
  const logEntries = useAgentLogs(task, isLoading);
  const logsScrollRef = useRef<HTMLDivElement>(null);
  const steps = activeTab === 'steps' ? (task?.steps || []) : [];
  const showSkeleton = isLoading && steps.length === 0;
  const prevReportsLen = useRef(0);

  useEffect(() => {
    const el = logsScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logEntries.length]);

  useEffect(() => {
    const n = task?.reports?.length ?? 0;
    if (n > 0 && prevReportsLen.current === 0) setActiveTab('report');
    prevReportsLen.current = n;
  }, [task?.reports?.length, setActiveTab]);

  return (
    <div className="w-80 border-l border-border flex flex-col shrink-0 bg-muted/30">
      {/* Tab switcher */}
      <div className="flex border-b border-border shrink-0 bg-background">
        {(['logs', 'steps', 'history', 'report'] as const).map((tab) => (
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
            {tab === 'logs' && logEntries.length > 0 && (
              <Badge variant="outline" className="ml-1.5 text-[9px] px-1 py-0 h-4">
                {logEntries.length}
              </Badge>
            )}
            {tab === 'steps' && task && (
              <Badge variant="outline" className="ml-1.5 text-[9px] px-1 py-0 h-4">
                {task.steps.length}
              </Badge>
            )}
            {tab === 'history' && history.length > 0 && (
              <Badge variant="outline" className="ml-1.5 text-[9px] px-1 py-0 h-4">
                {history.length}
              </Badge>
            )}
            {tab === 'report' && task?.reports && task.reports.length > 0 && (
              <Badge variant="outline" className="ml-1.5 text-[9px] px-1 py-0 h-4">
                {task.reports.length}
              </Badge>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col min-h-0">
        {activeTab === 'logs' ? (
          <>
            <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b border-border">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                <Terminal className="h-3.5 w-3.5" />
                Agent logs
              </span>
              {logEntries.length > 0 && (
                <span className="text-[10px] font-mono text-muted-foreground">{logEntries.length} entries</span>
              )}
            </div>
            <div
              ref={logsScrollRef}
              className="flex-1 overflow-y-auto overflow-x-hidden p-3 space-y-0 min-h-0"
            >
              {logEntries.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                  <Terminal className="h-8 w-8 opacity-20 mb-2" />
                  <p className="text-xs">No logs yet</p>
                </div>
              ) : (
                <AnimatePresence mode="popLayout">
                  <div className="space-y-2">
                    {logEntries.map((entry) => (
                      <LogEntryRow key={entry.id} entry={entry} />
                    ))}
                  </div>
                </AnimatePresence>
              )}
            </div>
            {task && task.status !== 'idle' && (
              <div className="shrink-0 border-t border-border px-3 py-2 flex items-center gap-2 text-xs text-muted-foreground">
                {task.status === 'running' || task.status === 'pending' ? (
                  <>
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                    Running...
                  </>
                ) : task.status === 'completed' ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    Completed
                  </>
                ) : task.status === 'failed' ? (
                  <>
                    <AlertCircle className="h-3.5 w-3.5 text-red-400" />
                    Error
                  </>
                ) : (
                  <>
                    <span className="h-2 w-2 rounded-full bg-muted-foreground" />
                    Cancelled
                  </>
                )}
              </div>
            )}
          </>
        ) : activeTab === 'steps' ? (
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
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
          </div>
        ) : activeTab === 'report' ? (
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {task?.reports && task.reports.length > 0 && task.sessionId ? (
              <ReportCardList reports={task.reports} sessionId={task.sessionId} />
            ) : (
              <div className="flex items-center justify-center h-full">
                <p className="text-xs text-muted-foreground">No reports yet</p>
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {history.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <p className="text-xs text-muted-foreground">No history yet</p>
              </div>
            ) : (
              history.map((t, i) => (
                <HistoryTaskCard key={t.sessionId || i} task={t} />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
