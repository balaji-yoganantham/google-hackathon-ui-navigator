@echo off
REM Run the Percept Python backend (Windows: uses ProactorEventLoop via run_server.py)
cd /d "%~dp0backend"
..\venv\Scripts\python run_server.py
pause
