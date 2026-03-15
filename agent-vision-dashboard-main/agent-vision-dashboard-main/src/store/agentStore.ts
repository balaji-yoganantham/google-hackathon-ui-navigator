import { create } from 'zustand';
import { mapBackendTask, type BackendTask } from '@/lib/api';

// Matches all action types the backend can produce
export type ActionType =
  | 'click' | 'type' | 'scroll' | 'navigate'
  | 'wait' | 'extract' | 'hover' | 'press' | 'screenshot';

export interface ExecutionStep {
  stepNumber: number;
  actionType: ActionType;
  reasoning: string;
  result: 'success' | 'fail' | 'pending';
  screenshotUrl?: string;
  beforeScreenshotUrl?: string;
  timestamp: string;
}

export interface AgentTask {
  sessionId: string;
  taskDescription: string;
  startUrl?: string;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'cancelled' | 'pending';
  steps: ExecutionStep[];
  currentScreenshot?: string;
  error?: string;
  startedAt?: string;
  completedAt?: string;
}

interface AgentStore {
  task: AgentTask | null;
  isLoading: boolean;
  isRecording: boolean;
  taskDescription: string;
  activeTab: 'current' | 'history';
  history: AgentTask[];
  /** Screenshot of the step the user clicked — shown in the main viewport. */
  selectedStepScreenshot: string | null;
  /** Session ID being continued from history (null = fresh execute mode). */
  continuingSessionId: string | null;

  setTaskDescription: (desc: string) => void;
  setIsLoading: (loading: boolean) => void;
  setIsRecording: (recording: boolean) => void;
  setTask: (task: AgentTask | null) => void;
  setActiveTab: (tab: 'current' | 'history') => void;
  setSelectedStepScreenshot: (url: string | null) => void;
  /** Enter continue-mode for a past task: pre-fills session ID. */
  startContinue: (task: AgentTask) => void;
  /** Exit continue-mode (back to fresh execute). */
  clearContinue: () => void;
  addStep: (step: ExecutionStep) => void;
  updateScreenshot: (url: string) => void;
  /**
   * Primary update path: replace task state from a raw backend TaskExecution payload.
   * Maps backend fields (base64 screenshots, string results, action.type) to frontend shape.
   */
  updateFromBackendTask: (raw: BackendTask) => void;
  completeTask: () => void;
  failTask: (error: string) => void;
  cancelTask: () => void;
  reset: () => void;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  task: null,
  isLoading: false,
  isRecording: false,
  taskDescription: '',
  activeTab: 'current',
  history: [],
  selectedStepScreenshot: null,
  continuingSessionId: null,

  setTaskDescription: (desc) => set({ taskDescription: desc }),
  setIsLoading: (loading) => set({ isLoading: loading }),
  setIsRecording: (recording) => set({ isRecording: recording }),
  setTask: (task) => set({ task }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setSelectedStepScreenshot: (url) => set({ selectedStepScreenshot: url }),

  startContinue: (task) => set({
    continuingSessionId: task.sessionId,
    taskDescription: '',
    activeTab: 'current',
  }),

  clearContinue: () => set({ continuingSessionId: null, taskDescription: '' }),

  addStep: (step) => set((state) => ({
    task: state.task ? { ...state.task, steps: [...state.task.steps, step] } : state.task,
  })),

  updateScreenshot: (url) => set((state) => ({
    task: state.task ? { ...state.task, currentScreenshot: url } : state.task,
  })),

  updateFromBackendTask: (raw) => set((state) => {
    if (!state.task) return {};
    const mapped = mapBackendTask(raw);
    return {
      task: {
        ...state.task,
        status: mapped.status as AgentTask['status'],
        steps: mapped.steps as ExecutionStep[],
        currentScreenshot: mapped.currentScreenshot,
        error: mapped.error,
        taskDescription: mapped.taskDescription || state.task.taskDescription,
        startUrl: mapped.startUrl ?? state.task.startUrl,
      },
    };
  }),

  completeTask: () => set((state) => {
    const completed = state.task
      ? { ...state.task, status: 'completed' as const, completedAt: new Date().toISOString() }
      : null;
    return {
      task: completed,
      isLoading: false,
      continuingSessionId: null,
      history: completed ? [completed, ...state.history] : state.history,
    };
  }),

  failTask: (error) => set((state) => {
    const failed = state.task ? { ...state.task, status: 'failed' as const, error } : null;
    return {
      task: failed,
      isLoading: false,
      continuingSessionId: null,
      history: failed ? [failed, ...state.history] : state.history,
    };
  }),

  cancelTask: () => set((state) => {
    const cancelled = state.task ? { ...state.task, status: 'cancelled' as const } : null;
    return {
      task: cancelled,
      isLoading: false,
      continuingSessionId: null,
      history: cancelled ? [cancelled, ...state.history] : state.history,
    };
  }),

  reset: () => set({ task: null, isLoading: false, taskDescription: '', continuingSessionId: null, selectedStepScreenshot: null }),
}));
