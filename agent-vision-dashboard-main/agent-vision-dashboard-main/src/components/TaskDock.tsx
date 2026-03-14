import { Mic, Send, Square, Loader2, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useAgentStore } from "@/store/agentStore";
import { executeTask, continueTask, cancelTask, createSSEStream, pollStatus, mapBackendTask, type BackendTask } from "@/lib/api";
import { useCallback, useRef } from "react";

export function TaskDock() {
  const {
    taskDescription, isLoading, isRecording, task, continuingSessionId,
    setTaskDescription, setIsLoading, setIsRecording,
    setTask, updateFromBackendTask, completeTask, failTask, cancelTask: storeCancelTask,
    clearContinue,
  } = useAgentStore();

  const recognitionRef = useRef<any>(null);
  const cleanupSSERef = useRef<(() => void) | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Polling fallback ───────────────────────────────────────────────────────
  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback((sessionId: string) => {
    if (pollRef.current) return;
    let attempts = 0;
    const MAX = 300;

    pollRef.current = setInterval(async () => {
      if (attempts++ >= MAX) { stopPolling(); setIsLoading(false); return; }
      try {
        const raw: BackendTask = await pollStatus(sessionId);
        updateFromBackendTask(raw);
        if (raw.status === 'completed') {
          completeTask();
          stopPolling();
        } else if (raw.status === 'failed') {
          failTask(raw.error || 'Task failed');
          stopPolling();
        } else if (raw.status === 'cancelled') {
          storeCancelTask();
          stopPolling();
        }
      } catch {
        // ignore transient errors
      }
    }, 2000);
  }, [stopPolling, setIsLoading, updateFromBackendTask, completeTask, failTask, storeCancelTask]);

  // ── SSE helper shared by execute and continue ─────────────────────────────
  const attachStream = useCallback((sessionId: string) => {
    cleanupSSERef.current = createSSEStream(
      sessionId,
      (raw: BackendTask) => {
        updateFromBackendTask(raw);
        if (raw.status === 'completed') {
          completeTask();
          cleanupSSERef.current?.();
          cleanupSSERef.current = null;
        } else if (raw.status === 'failed') {
          failTask(raw.error || 'Task failed');
          cleanupSSERef.current?.();
          cleanupSSERef.current = null;
        } else if (raw.status === 'cancelled') {
          storeCancelTask();
          cleanupSSERef.current?.();
          cleanupSSERef.current = null;
        }
      },
      () => {
        console.warn('[TaskDock] SSE failed — falling back to polling');
        cleanupSSERef.current = null;
        startPolling(sessionId);
      },
    );
  }, [updateFromBackendTask, completeTask, failTask, storeCancelTask, startPolling]);

  // ── Send ───────────────────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    if (!taskDescription || isLoading) return;

    cleanupSSERef.current?.();
    stopPolling();
    setIsLoading(true);

    try {
      if (continuingSessionId) {
        // ── Continue from a previous session ──────────────────────────────
        const { sessionId, task: taskData } = await continueTask(continuingSessionId, taskDescription);
        const mapped = mapBackendTask(taskData);
        setTask({
          sessionId,
          taskDescription: mapped.taskDescription || taskDescription,
          startUrl: mapped.startUrl,
          status: mapped.status as 'running',
          steps: mapped.steps as import('@/store/agentStore').ExecutionStep[],
          startedAt: new Date().toISOString(),
          currentNode: mapped.currentNode,
          planSummary: mapped.planSummary,
          planDecisions: mapped.planDecisions,
          currentDecisionIndex: mapped.currentDecisionIndex,
          currentScreenshot: mapped.currentScreenshot,
        });
        attachStream(sessionId);
      } else {
        // ── Fresh task ────────────────────────────────────────────────────
        setTask({
          sessionId: '',
          taskDescription,
          status: 'running',
          steps: [],
          startedAt: new Date().toISOString(),
        });
        const { sessionId, task: taskData } = await executeTask(taskDescription);
        const mapped = mapBackendTask(taskData);
        setTask({
          sessionId,
          taskDescription: mapped.taskDescription || taskDescription,
          startUrl: mapped.startUrl,
          status: (mapped.status === 'pending' || mapped.status === 'running' ? mapped.status : 'running') as 'running',
          steps: mapped.steps as import('@/store/agentStore').ExecutionStep[],
          startedAt: new Date().toISOString(),
          currentNode: mapped.currentNode,
          planSummary: mapped.planSummary,
          planDecisions: mapped.planDecisions,
          currentDecisionIndex: mapped.currentDecisionIndex,
          currentScreenshot: mapped.currentScreenshot,
        });
        attachStream(sessionId);
      }
    } catch (err: any) {
      failTask(err.message || 'Failed to start task');
      stopPolling();
    }
  }, [taskDescription, isLoading, continuingSessionId, stopPolling, attachStream,
      setIsLoading, setTask, failTask]);

  // ── Stop ───────────────────────────────────────────────────────────────────
  const handleStop = useCallback(async () => {
    cleanupSSERef.current?.();
    cleanupSSERef.current = null;
    stopPolling();
    if (task?.sessionId) {
      try { await cancelTask(task.sessionId); } catch { /* ignore */ }
    }
    storeCancelTask();
  }, [task?.sessionId, stopPolling, storeCancelTask]);

  // ── Voice ──────────────────────────────────────────────────────────────────
  const handleSpeak = useCallback(() => {
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    recognition.onresult = (e: any) => {
      const transcript = e.results[0][0].transcript;
      setTaskDescription(taskDescription ? `${taskDescription} ${transcript}` : transcript);
      setIsRecording(false);
    };
    recognition.onerror = () => setIsRecording(false);
    recognition.onend = () => setIsRecording(false);
    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
  }, [isRecording, taskDescription, setTaskDescription, setIsRecording]);

  // ── UI ─────────────────────────────────────────────────────────────────────
  return (
    <div className="p-4 pt-2">
      <div className="rounded-lg bg-card border border-border p-4 space-y-3">

        {/* Continue mode banner */}
        {continuingSessionId && (
          <div className="flex items-center gap-2 rounded-md bg-primary/10 border border-primary/30 px-3 py-2">
            <RotateCcw className="h-3.5 w-3.5 text-primary shrink-0" />
            <p className="text-[11px] text-primary flex-1">
              Continuing from previous session
              <span className="ml-1 font-mono opacity-70">#{continuingSessionId.slice(0, 8)}</span>
            </p>
            <button
              onClick={clearContinue}
              className="text-primary/60 hover:text-primary transition-colors"
              title="Cancel continue mode"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              {continuingSessionId ? 'Follow-up Instruction' : 'Task Description'}
            </label>
            {isRecording && (
              <Badge className="bg-destructive/20 text-destructive border-destructive/30 text-[10px] gap-1 font-mono">
                <span className="h-1.5 w-1.5 rounded-full bg-destructive pulse-recording inline-block" />
                Recording...
              </Badge>
            )}
          </div>
          <Textarea
            placeholder={
              continuingSessionId
                ? "What should the agent do next?"
                : "Describe what you want the agent to do..."
            }
            value={taskDescription}
            onChange={(e) => setTaskDescription(e.target.value)}
            className="text-xs bg-secondary border-border min-h-[60px] resize-none"
            rows={2}
            disabled={isLoading}
          />
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSpeak}
            className={`gap-1.5 text-xs ${isRecording ? 'border-destructive text-destructive' : ''}`}
          >
            <Mic className="h-3.5 w-3.5" />
            {isRecording ? 'Stop' : 'Speak'}
          </Button>

          <Button
            size="sm"
            onClick={handleSend}
            disabled={isLoading || !taskDescription}
            className={`gap-1.5 text-xs flex-1 ${continuingSessionId ? 'bg-primary/80 hover:bg-primary' : ''}`}
          >
            {isLoading
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
              : continuingSessionId
                ? <RotateCcw className="h-3.5 w-3.5" />
                : <Send className="h-3.5 w-3.5" />}
            {isLoading ? 'Running...' : continuingSessionId ? 'Continue' : 'Send'}
          </Button>

          <Button
            variant="destructive"
            size="sm"
            onClick={handleStop}
            disabled={!isLoading}
            className="gap-1.5 text-xs"
          >
            <Square className="h-3 w-3" />
            Stop
          </Button>
        </div>
      </div>
    </div>
  );
}
