"""
Entry-point for UI Navigator backend.

Sets WindowsProactorEventLoopPolicy BEFORE uvicorn creates the event loop,
so Playwright can spawn its Chromium subprocess on Windows.
"""
import asyncio
import sys

# Must be set before uvicorn.run() creates the event loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn  # noqa: E402 (import after policy set intentionally)
from config import settings  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.BACKEND_PORT,
        reload=False,   # reload forks a new process — use False here
        log_level="info",
    )
