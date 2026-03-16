// API base URL. If VITE_API_URL is set (non-empty), use it directly.
// In production, if unset, fall back to the deployed Cloud Run backend so the hosted app works.
// In dev, if empty use '' so /api/* goes through the Vite dev proxy → localhost:8000.
const VITE_URL: string = import.meta.env.VITE_API_URL ?? '';
const PROD_BACKEND_URL = 'https://percept-backend-94139147538.us-central1.run.app';
const API_BASE =
  VITE_URL.trim() !== ''
    ? VITE_URL
    : import.meta.env.PROD
      ? PROD_BACKEND_URL
      : '';

// ─── Backend types (matching Python schemas.py) ──────────────────────────────

export interface BackendAction {
  type: 'click' | 'type' | 'scroll' | 'navigate' | 'wait' | 'screenshot' | 'hover' | 'press' | 'extract';
  selector?: string;
  text?: string;
  url?: string;
  amount?: number;
  delay?: number;
  key?: string;
}

export interface ContentReport {
  title: string;
  url: string;
  date?: string;
  content_type: string;
  content: string;
  court?: string;
  docket?: string;
}

export interface ExtractionResult {
  reports: ContentReport[];
  session_id: string;
}

export interface BackendStep {
  stepNumber: number;
  description: string;
  action: BackendAction;
  screenshot: string;        // raw base64 jpeg (after action)
  beforeScreenshot?: string;  // raw base64 jpeg (before action)
  reasoning: string;
  result: string;             // e.g. "Clicked on ...", "Failed: ..."
  timestamp: string;
}

export interface BackendTask {
  id: string;
  taskDescription: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  steps: BackendStep[];
  currentScreenshot: string;  // raw base64 jpeg
  error?: string;
  finalAnswer?: string;       // agent's final answer when task completes with no further actions
  startUrl?: string;
  reports?: ContentReport[];
  createdAt: string;
  updatedAt: string;
}

// ─── Transformer helpers ──────────────────────────────────────────────────────

/** Wrap raw base64 into a valid img src. Noop if already a data-URL. */
export function toDataUrl(b64: string): string {
  if (!b64) return '';
  if (b64.startsWith('data:')) return b64;
  return `data:image/jpeg;base64,${b64}`;
}

/** Map backend result string → frontend result token. */
function mapResult(result: string): 'success' | 'fail' | 'pending' {
  if (!result) return 'pending';
  return result.toLowerCase().startsWith('failed') ? 'fail' : 'success';
}

/** Convert a full BackendTask into the shape the frontend store expects. */
export function mapBackendTask(raw: BackendTask) {
  return {
    id: raw.id,
    taskDescription: raw.taskDescription,
    status: raw.status,
    startUrl: raw.startUrl,
    error: raw.error,
    finalAnswer: raw.finalAnswer,
    currentScreenshot: raw.currentScreenshot ? toDataUrl(raw.currentScreenshot) : undefined,
    reports: raw.reports ?? [],
    steps: (raw.steps || []).map((s) => ({
      stepNumber: s.stepNumber,
      actionType: (s.action?.type ?? 'click') as BackendAction['type'],
      reasoning: s.reasoning || s.description || '',
      result: mapResult(s.result),
      screenshotUrl: s.screenshot ? toDataUrl(s.screenshot) : undefined,
      beforeScreenshotUrl: s.beforeScreenshot ? toDataUrl(s.beforeScreenshot) : undefined,
      timestamp: s.timestamp || new Date().toISOString(),
    })),
  };
}

// ─── API calls ────────────────────────────────────────────────────────────────

/** Send raw audio to backend; returns { url, goal } for the agent. */
export async function transcribeAudio(audioBase64: string, mimeType: string = 'audio/webm'): Promise<{ url: string; goal: string }> {
  const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audioBase64, mimeType }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || 'Transcription failed');
  }
  return res.json();
}

/** Fetch extraction reports for a session. */
export async function getReport(sessionId: string): Promise<ExtractionResult> {
  const res = await fetch(`${API_BASE}/api/agent/report/${sessionId}`);
  if (!res.ok) throw new Error('Failed to fetch report');
  return res.json();
}

/** Download session report as .docx. */
export async function exportDocx(sessionId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/agent/export/${sessionId}`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to export report');
  return res.blob();
}

export async function executeTask(taskDescription: string, startUrl?: string) {
  const res = await fetch(`${API_BASE}/api/agent/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taskDescription, startUrl: startUrl ?? '' }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || 'Failed to start task');
  }
  return res.json() as Promise<{ sessionId: string; task: BackendTask }>;
}

export async function continueTask(sessionId: string, instruction: string) {
  const res = await fetch(`${API_BASE}/api/agent/continue/${sessionId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || 'Failed to continue task');
  }
  return res.json() as Promise<{ sessionId: string; task: BackendTask }>;
}

export async function cancelTask(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/agent/cancel/${sessionId}`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to cancel task');
  return res.json();
}

/**
 * Build the WebSocket URL for the live browser stream of a session.
 * Handles dev (Vite proxy) and production (direct wss://...) environments.
 */
export function getBrowserStreamUrl(sessionId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const apiBase = (import.meta.env.VITE_API_URL ?? '').trim();
  const wsBase = apiBase
    ? apiBase.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:')
    : `${protocol}//${window.location.host}`;
  return `${wsBase}/api/agent/ws/${sessionId}`;
}

export function createSSEStream(
  sessionId: string,
  onMessage: (data: BackendTask) => void,
  onError: () => void,
) {
  const source = new EventSource(`${API_BASE}/api/agent/stream/${sessionId}`);
  source.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      // ignore JSON parse errors
    }
  };
  source.onerror = () => {
    source.close();
    onError();
  };
  return () => source.close();
}

export async function pollStatus(sessionId: string): Promise<BackendTask> {
  const res = await fetch(`${API_BASE}/api/agent/status/${sessionId}`);
  if (!res.ok) throw new Error('Failed to fetch status');
  return res.json();
}
