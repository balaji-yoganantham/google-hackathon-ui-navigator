import { motion } from "framer-motion";
import { Mic, Send, Square, Loader2, RotateCcw, X, Sparkles, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useAgentStore } from "@/store/agentStore";
import { executeTask, continueTask, cancelTask, createSSEStream, pollStatus, transcribeAudio, getReport, type BackendTask } from "@/lib/api";
import { useCallback, useEffect, useRef, useState } from "react";

/** Speak text via Web Speech API (for step narration and summary). */
function speakMessage(text: string) {
  try {
    if (!window.speechSynthesis || !text?.trim()) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.trim().slice(0, 200));
    u.rate = 1.05;
    u.pitch = 1;
    window.speechSynthesis.speak(u);
  } catch {}
}

export function TaskDock() {
  const {
    taskDescription, isLoading, isRecording, task, continuingSessionId, triggerSend, setTriggerSend,
    setTaskDescription, setIsLoading, setIsRecording,
    setTask, updateFromBackendTask, completeTask, failTask, cancelTask: storeCancelTask,
    clearContinue, reset,
  } = useAgentStore();
  const [continueInstruction, setContinueInstruction] = useState("");
  const [volumeLevel, setVolumeLevel] = useState(0);
  const [isAutoStopping, setIsAutoStopping] = useState(false);

  const cleanupSSERef = useRef<(() => void) | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastSpokenStepCountRef = useRef(0);

  // Voice: MediaRecorder + VAD (silence detection)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const silenceStartRef = useRef<number | null>(null);
  const hasSpokenRef = useRef(false);
  const stoppingRef = useRef(false);
  const SILENCE_THRESHOLD = 25;
  const SILENCE_DURATION_MS = 3000;

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
        const steps = raw.steps ?? [];
        const stepCount = steps.length;
        if (stepCount > lastSpokenStepCountRef.current) {
          for (let i = lastSpokenStepCountRef.current; i < stepCount; i++) {
            const step = steps[i];
            const text = (step?.result || step?.reasoning || "").trim().slice(0, 80);
            if (text) speakMessage(`Step ${i + 1}: ${text}`);
          }
          lastSpokenStepCountRef.current = stepCount;
        }
        if (raw.status === 'completed') {
          if (!raw.reports?.length) {
            try {
              const { reports } = await getReport(sessionId);
              if (reports?.length) updateFromBackendTask({ ...raw, reports });
            } catch {
              // ignore
            }
          }
          const summary = (raw.finalAnswer || "").trim().slice(0, 150) || `Task completed in ${raw.steps?.length ?? 0} steps.`;
          speakMessage(raw.reports?.length ? `${summary} Report is ready.` : summary);
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
      async (raw: BackendTask) => {
        updateFromBackendTask(raw);
        const steps = raw.steps ?? [];
        const stepCount = steps.length;
        if (stepCount > lastSpokenStepCountRef.current) {
          for (let i = lastSpokenStepCountRef.current; i < stepCount; i++) {
            const step = steps[i];
            const text = (step?.result || step?.reasoning || "").trim().slice(0, 80);
            if (text) speakMessage(`Step ${i + 1}: ${text}`);
          }
          lastSpokenStepCountRef.current = stepCount;
        }
        if (raw.status === 'completed') {
          if (!raw.reports?.length && raw.id) {
            try {
              const { reports } = await getReport(raw.id);
              if (reports?.length) updateFromBackendTask({ ...raw, reports });
            } catch {
              // ignore; task already has latest from stream
            }
          }
          const summary = (raw.finalAnswer || "").trim().slice(0, 150) || `Task completed in ${raw.steps?.length ?? 0} steps.`;
          speakMessage(raw.reports?.length ? `${summary} Report is ready.` : summary);
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
    lastSpokenStepCountRef.current = 0;
    setIsLoading(true);

    try {
      if (continuingSessionId) {
        // ── Continue from a previous session ──────────────────────────────
        const { sessionId, task: taskData } = await continueTask(continuingSessionId, taskDescription);
        setTask({
          sessionId,
          taskDescription: taskData.taskDescription || taskDescription,
          startUrl: taskData.startUrl,
          status: 'running',
          steps: taskData.steps?.length
            ? (taskData.steps as any)
            : [],
          startedAt: new Date().toISOString(),
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
        setTask({
          sessionId,
          taskDescription: taskData.taskDescription || taskDescription,
          startUrl: taskData.startUrl,
          status: 'running',
          steps: [],
          startedAt: new Date().toISOString(),
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

  // ── Continue in current session (follow-up instruction) ────────────────────
  const handleContinueInSession = useCallback(async () => {
    if (!continueInstruction.trim() || !task?.sessionId || isLoading) return;
    const instruction = continueInstruction.trim();
    cleanupSSERef.current?.();
    stopPolling();
    lastSpokenStepCountRef.current = 0;
    setIsLoading(true);
    setContinueInstruction("");
    try {
      const { sessionId, task: taskData } = await continueTask(task.sessionId, instruction);
      setTask({
        sessionId,
        taskDescription: taskData.taskDescription || instruction,
        startUrl: taskData.startUrl ?? task.startUrl,
        status: "running",
        steps: task.steps,
        currentScreenshot: task.currentScreenshot,
        startedAt: new Date().toISOString(),
      });
      attachStream(sessionId);
    } catch (err: any) {
      failTask(err.message || "Failed to continue");
      stopPolling();
    }
  }, [continueInstruction, task, isLoading, stopPolling, attachStream, setIsLoading, setTask, failTask]);

  // ── Clean up stream when task is cleared (e.g. New Task from header) ───────
  useEffect(() => {
    if (task == null && cleanupSSERef.current) {
      cleanupSSERef.current();
      cleanupSSERef.current = null;
      stopPolling();
      setContinueInstruction("");
    }
  }, [task, stopPolling]);

  // ── Trigger send from Planner "Start Task" ──────────────────────────────────
  useEffect(() => {
    if (!triggerSend || !taskDescription?.trim() || isLoading) return;
    setTriggerSend(false);
    handleSend();
  }, [triggerSend]); // eslint-disable-line react-hooks/exhaustive-deps -- only run when triggerSend flips

  // ── Voice: MediaRecorder + VAD ─────────────────────────────────────────────
  const cleanupAudio = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {}
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    silenceStartRef.current = null;
    hasSpokenRef.current = false;
  }, []);

  const stopRecording = useCallback(() => {
    if (stoppingRef.current) return;
    stoppingRef.current = true;
    setVolumeLevel(0);
    cleanupAudio();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }, [cleanupAudio]);

  const runTaskWithGoalAndUrl = useCallback(
    async (goal: string, startUrl: string) => {
      if (!goal.trim() || isLoading) return;
      cleanupSSERef.current?.();
      stopPolling();
      setIsLoading(true);
      clearContinue();
      try {
        setTask({
          sessionId: '',
          taskDescription: goal,
          status: 'running',
          steps: [],
          startedAt: new Date().toISOString(),
        });
        const { sessionId, task: taskData } = await executeTask(goal, startUrl || '');
        setTask({
          sessionId,
          taskDescription: taskData.taskDescription || goal,
          startUrl: taskData.startUrl || startUrl,
          status: 'running',
          steps: [],
          startedAt: new Date().toISOString(),
        });
        setTaskDescription(goal);
        attachStream(sessionId);
      } catch (err: unknown) {
        failTask(err instanceof Error ? err.message : 'Failed to start task');
        stopPolling();
      }
    },
    [isLoading, stopPolling, setTask, setTaskDescription, failTask, attachStream, clearContinue]
  );

  const startRecording = useCallback(async () => {
    try {
      stoppingRef.current = false;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : 'audio/mp4';
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        const blob = new Blob(chunksRef.current, { type: mimeType });
        if (blob.size < 1000) return;
        setIsAutoStopping(true);
        setTimeout(() => {
          setIsAutoStopping(false);
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64 = (reader.result as string).split(',')[1];
            if (base64) {
              const simpleMime = mimeType.split(';')[0];
              transcribeAudio(base64, simpleMime)
                .then(({ url, goal: g }) => {
                  setTaskDescription(g || '');
                  if (g && g.trim()) runTaskWithGoalAndUrl(g.trim(), url || '');
                })
                .catch(() => {
                  setTaskDescription('');
                });
            }
          };
          reader.readAsDataURL(blob);
        }, 600);
      };
      mediaRecorderRef.current = recorder;
      recorder.start(250);
      setIsRecording(true);
      hasSpokenRef.current = false;
      silenceStartRef.current = null;
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.3;
      source.connect(analyser);
      analyserRef.current = analyser;
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const monitorVolume = () => {
        if (!analyserRef.current || stoppingRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
        const avg = sum / dataArray.length;
        setVolumeLevel(Math.min(avg / 80, 1));
        if (avg > SILENCE_THRESHOLD) {
          hasSpokenRef.current = true;
          silenceStartRef.current = null;
        } else if (hasSpokenRef.current) {
          if (!silenceStartRef.current) silenceStartRef.current = Date.now();
          else if (Date.now() - (silenceStartRef.current || 0) >= SILENCE_DURATION_MS) {
            stopRecording();
            return;
          }
        }
        rafRef.current = requestAnimationFrame(monitorVolume);
      };
      rafRef.current = requestAnimationFrame(monitorVolume);
    } catch {
      cleanupAudio();
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      mediaRecorderRef.current = null;
      setIsRecording(false);
    }
  }, [stopRecording, cleanupAudio, runTaskWithGoalAndUrl]);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (audioContextRef.current) {
        try {
          audioContextRef.current.close();
        } catch {}
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch {}
      }
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const handleSpeak = useCallback(() => {
    if (isRecording) {
      stopRecording();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      alert('Microphone access is not supported in this browser.');
      return;
    }
    startRecording();
  }, [isRecording, stopRecording, startRecording]);

  const SUGGESTIONS = [
    "Search for something and tell me the results",
    "Extract a report from this page",
    "Navigate to a URL and summarize the page",
  ];

  // ── UI: full-width command bar ──────────────────────────────────────────────
  return (
    <div className="shrink-0 border-t border-border bg-muted/40">
      <div className="max-w-4xl mx-auto w-full px-6 py-4 space-y-4">
        {/* Suggestion chips — same horizontal bounds as command block */}
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="flex flex-wrap gap-2 w-full"
        >
          {SUGGESTIONS.map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setTaskDescription(s)}
              className="text-xs px-3 py-1.5 rounded-full border border-border bg-background text-muted-foreground hover:text-foreground hover:border-primary/40 hover:bg-primary/5 transition-colors"
            >
              {s}
            </button>
          ))}
        </motion.div>

        {/* Continue mode banner */}
        {continuingSessionId && (
          <div className="flex items-center gap-2 rounded-lg bg-primary/10 border border-primary/20 px-3 py-2">
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

        {/* Main command row — label, input, and buttons on a single aligned grid */}
        <div className="flex flex-col gap-1.5 w-full">
          <div className="flex items-center gap-2">
            <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              {continuingSessionId ? "Follow-up Instruction" : "AI command"}
            </label>
            {isRecording && (
              <Badge className="bg-destructive/20 text-destructive border-destructive/30 text-[10px] gap-1 font-mono">
                <span className="h-1.5 w-1.5 rounded-full bg-destructive pulse-recording inline-block" />
                Recording...
              </Badge>
            )}
          </div>
          <div className="flex items-end gap-2 w-full">
            <Textarea
              placeholder={
                continuingSessionId
                  ? "What should the agent do next?"
                  : "Describe what you want the agent to do..."
              }
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              className="rounded-lg border border-border bg-background min-h-[52px] resize-none text-sm flex-1 min-w-0"
              rows={2}
              disabled={isLoading}
            />
            {/* Fixed-width button column so Continue row aligns with this row */}
            <div className="flex items-center gap-2 shrink-0 w-[200px] justify-end h-[52px] items-end pb-0.5">
            <div className="relative">
              {isRecording && !isAutoStopping && (
                <div
                  className="absolute inset-0 rounded-lg bg-red-500/10 border border-red-400/30 -m-1 transition-transform duration-75"
                  style={{ transform: `scale(${1 + volumeLevel * 0.5})` }}
                />
              )}
              {isAutoStopping && (
                <div className="absolute inset-0 rounded-lg bg-emerald-500/20 border border-emerald-400/50 -m-1 animate-ping" />
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={handleSpeak}
                className={`relative gap-1.5 text-xs h-9 ${
                  isAutoStopping
                    ? "border-emerald-400 text-emerald-600 bg-emerald-500/20"
                    : isRecording
                      ? "border-destructive text-destructive bg-destructive/20"
                      : ""
                }`}
              >
                {isAutoStopping ? <Zap className="h-3.5 w-3.5 animate-pulse" /> : <Mic className="h-3.5 w-3.5" />}
                {isAutoStopping ? "Sending…" : isRecording ? "Stop" : "Speak"}
              </Button>
            </div>
            <Button
              size="sm"
              onClick={handleSend}
              disabled={isLoading || !taskDescription}
              className="gap-1.5 text-xs h-9 flex-1 min-w-[80px] bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              {isLoading
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : continuingSessionId
                  ? <RotateCcw className="h-3.5 w-3.5" />
                  : <Send className="h-3.5 w-3.5" />}
              {isLoading ? "Running…" : continuingSessionId ? "Continue" : "Send"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleStop}
              disabled={!isLoading}
              className="gap-1.5 text-xs h-9 border-destructive/50 text-destructive hover:bg-destructive/10"
            >
              <Square className="h-3 w-3" />
              Stop
            </Button>
            </div>
          </div>
        </div>

        {/* Final answer */}
        {task?.finalAnswer && (
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold text-primary uppercase tracking-wider">
              <Sparkles className="h-3.5 w-3.5 shrink-0" />
              Agent Answer
            </div>
            <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words">
              {task.finalAnswer}
            </p>
          </div>
        )}

        {/* Continue in session — same textarea width and Send position as main row */}
        {task?.sessionId && ["completed", "failed", "cancelled"].includes(task.status) && (
          <div className="flex flex-col gap-1.5 w-full">
            <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Continue in session
            </label>
            <div className="flex items-end gap-2 w-full">
              <Textarea
                placeholder="What should the agent do next in this session?"
                value={continueInstruction}
                onChange={(e) => setContinueInstruction(e.target.value)}
                className="flex-1 min-w-0 rounded-lg border border-border bg-background min-h-[44px] resize-none text-sm"
                rows={1}
                disabled={isLoading}
              />
              {/* Same width as main row button column so Send aligns vertically */}
              <div className="shrink-0 w-[200px] flex justify-end h-[44px] items-end pb-0.5">
                <Button
                  size="sm"
                  onClick={handleContinueInSession}
                  disabled={isLoading || !continueInstruction.trim()}
                  className="gap-1.5 text-xs h-9"
                >
                  {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  Send
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
