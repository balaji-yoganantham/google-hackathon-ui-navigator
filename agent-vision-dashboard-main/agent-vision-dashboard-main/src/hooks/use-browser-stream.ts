/**
 * useBrowserStream — connects to the backend WebSocket live browser feed.
 *
 * While a session is active the backend pushes JPEG frames as JSON:
 *   { type: "screenshot", screenshot: "<base64>", step: N }
 *
 * The hook automatically:
 *  - Opens the socket when sessionId is provided and isActive is true
 *  - Reconnects every 3 s if the connection drops while still active
 *  - Closes cleanly when isActive becomes false or sessionId clears
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface BrowserFrame {
  type: 'screenshot';
  screenshot: string;
  step: number;
}

interface UseBrowserStreamResult {
  /** Latest JPEG frame as a data-URL, or empty string if none yet. */
  screenshot: string;
  connected: boolean;
}

export function useBrowserStream(
  sessionId: string | null | undefined,
  isActive: boolean,
): UseBrowserStreamResult {
  const [screenshot, setScreenshot] = useState('');
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const clearReconnect = () => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  const close = useCallback(() => {
    clearReconnect();
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const connect = useCallback(() => {
    if (!sessionId || !mountedRef.current) return;

    // Determine WS URL — handle Vite dev proxy and production
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // In production VITE_API_URL may be set (e.g. https://...run.app).
    // Convert it to wss://... for WebSocket.
    const apiBase = (import.meta.env.VITE_API_URL ?? '').trim();
    const wsBase = apiBase
      ? apiBase.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:')
      : `${protocol}//${window.location.host}`;

    const url = `${wsBase}/api/agent/ws/${sessionId}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const msg: BrowserFrame = JSON.parse(event.data as string);
        if (msg.type === 'screenshot' && msg.screenshot) {
          setScreenshot(`data:image/jpeg;base64,${msg.screenshot}`);
        }
      } catch { /* ignore malformed frames */ }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Reconnect if the task is still supposed to be running
      if (mountedRef.current && isActive) {
        reconnectTimerRef.current = setTimeout(() => connect(), 3_000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, isActive]);

  useEffect(() => {
    mountedRef.current = true;

    if (sessionId && isActive) {
      connect();
    } else {
      close();
      if (!isActive) {
        // Keep the last frame visible after task ends; clear on new task
        if (!sessionId) setScreenshot('');
      }
    }

    return () => {
      mountedRef.current = false;
      clearReconnect();
      if (wsRef.current) {
        try { wsRef.current.close(); } catch { /* ignore */ }
        wsRef.current = null;
      }
    };
  }, [sessionId, isActive, connect, close]);

  return { screenshot, connected };
}
