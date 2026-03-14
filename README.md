# UI Navigator

Python backend + React/Vite frontend for an AI web automation agent (Planner + Executor agents with Gemini 2.0 Flash).

## Backend (Python — using venv)

- **Location:** `backend/`
- **Stack:** FastAPI, LangChain, LangGraph, langchain-google-genai, Playwright, Pydantic v2
- **venv is at:** `ui_navigator/venv/`

### One-time setup (already done — venv and packages installed)
```powershell
# From ui_navigator/ folder
python -m venv venv
venv\Scripts\pip install -r backend\requirements.txt
venv\Scripts\playwright install chromium
```

### Configure
Edit `backend/.env` and replace `your-gemini-api-key-here` with your real [Google AI Studio](https://aistudio.google.com/app/apikey) API key:
```
GOOGLE_API_KEY=AIza...
```

### Run the backend
**Option A — batch file (easiest):** double-click `run_backend.bat`

**Option B — PowerShell:**
```powershell
.\run_backend.ps1
```

**Option C — manual:**
```powershell
cd backend
..\venv\Scripts\uvicorn main:app --reload --port 8000
```

- **API:** `http://localhost:8000`
- **Swagger docs:** `http://localhost:8000/docs`

## Frontend (React + Vite)

- **Generate with Lovable AI:** Open [Lovable](https://lovable.dev) and paste the prompt from `frontend/LOVABLE_PROMPT.md` to generate the React + Vite app.
- **After generation:** Set `VITE_API_URL=http://localhost:8000` (or in `.env`) and run `npm run dev` (default port 5173).

## Architecture

- **Planner Agent:** Screenshot + task → Gemini 2.0 Flash → structured action plan (JSON).
- **Executor Agent:** Runs one browser action via Playwright, returns result + new screenshot.
- **Orchestrator:** LangGraph StateGraph wires plan → execute loop with optional re-planning on failure.
