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

  setTaskDescription: (desc: string) => void;
  setIsLoading: (loading: boolean) => void;
  setIsRecording: (recording: boolean) => void;
  setTask: (task: AgentTask | null) => void;
  setActiveTab: (tab: 'current' | 'history') => void;
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

  setTaskDescription: (desc) => set({ taskDescription: desc }),
  setIsLoading: (loading) => set({ isLoading: loading }),
  setIsRecording: (recording) => set({ isRecording: recording }),
  setTask: (task) => set({ task }),
  setActiveTab: (tab) => set({ activeTab: tab }),

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
      history: completed ? [completed, ...state.history] : state.history,
    };
  }),

  failTask: (error) => set((state) => ({
    task: state.task ? { ...state.task, status: 'failed' as const, error } : state.task,
    isLoading: false,
  })),

  cancelTask: () => set((state) => ({
    task: state.task ? { ...state.task, status: 'cancelled' as const } : state.task,
    isLoading: false,
  })),

  reset: () => set({ task: null, isLoading: false, taskDescription: '' }),
}));
