# Lovable AI Frontend Prompt

Generate the React + Vite frontend by copying the prompt below into [Lovable AI](https://lovable.dev).

---

Build a modern React + Vite + TypeScript web app called **UI Navigator** — an AI web automation agent dashboard. Use Tailwind CSS and shadcn/ui components.

**Layout:** A full-screen dark-themed dashboard with three zones:

1. **Center panel ("Agent Vision")** — takes 60% of width. Shows a live screenshot of the browser the AI is controlling. Use a 16:9 aspect ratio container with a subtle border. Show a "Live" badge (green pulse dot) when the agent is running. When idle, show a centered placeholder with a globe icon and text "Enter a URL and task to begin".
2. **Bottom-left dock ("Task Dock")** — contains: (a) a URL text input labeled "Starting URL", (b) a multi-line text area for the task description, (c) a row of buttons: "Speak" (microphone icon, voice input via Web Speech API), "Send" (primary CTA, triggers task execution), "Stop" (danger, cancels running task). Disable Send when loading. Show a loading spinner on Send while running.
3. **Right side panel ("Logs & Debug")** — scrollable list of execution steps. Each step card shows: step number badge, action type chip (click/type/scroll/navigate), the AI's reasoning text, result (success/fail), and a small thumbnail of the screenshot. Show a skeleton loader when loading. Include a tab switcher at the top: "Current" and "History".

**Header:** Brand name "UI Navigator" + subtitle "Gemini Visual Agent". Right side: theme toggle (dark/light), "Sign In" button (Google, via Firebase Auth). When signed in, show avatar + display name + "Sign Out".

**State management:** Use React Query for API calls + Zustand for global state (current task, loading, session ID). Use EventSource (SSE) to stream live updates from `GET /api/agent/stream/{sessionId}`. Fall back to polling (`GET /api/agent/status/{sessionId}` every 2s) if SSE fails.

**API base URL:** Read from `import.meta.env.VITE_API_URL` (default `http://localhost:8000`).

**API calls:**
- `POST /api/agent/execute` with `{ taskDescription, startUrl }` → returns `{ sessionId, task }`
- `GET /api/agent/stream/{sessionId}` — SSE, each event is a full task JSON
- `POST /api/agent/cancel/{sessionId}` — cancel running task

**Multi-agent badge:** In the header subtitle area, add a small badge that reads "Planner + Executor Agents" to highlight the dual-agent architecture.

**Voice input:** On "Speak" click, use the browser Web Speech API to transcribe the user's voice and fill the task description textarea. Show a pulsing red "Recording..." badge while active.

**Success/error banners:** Show a green banner at the bottom when task completes ("Task completed in N steps"), red banner on failure with the error message.

**Responsive:** Works on screens 1024px and wider. The right panel collapses to a bottom sheet on mobile.

Use clean, minimal design: dark background `#0f1117`, card background `#1a1d27`, accent color `#6366f1` (indigo). Monospace font for logs. Smooth transitions on all state changes.
