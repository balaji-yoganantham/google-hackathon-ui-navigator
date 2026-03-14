"""UI Navigator Backend - FastAPI entry point."""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# Playwright on Windows requires ProactorEventLoop (SelectorEventLoop does not support subprocesses)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import agent, voice
from utils.browser_pool import browser_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: warm browser. Shutdown: close browser."""
    logger.info("Starting UI Navigator backend")
    try:
        await browser_pool.initialize()
        logger.info("Browser pre-warmed")
    except Exception as e:
        logger.warning("Browser pre-warm failed: %s (will retry on first request)", e)
    yield
    await browser_pool.close()
    logger.info("Browser closed")


app = FastAPI(
    title="UI Navigator API",
    description="AI web automation agent - Planner + Executor agents with Gemini 2.0 Flash",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # Vite default dev port (agent-vision-dashboard uses 8080)
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(agent.router)
app.include_router(voice.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.BACKEND_PORT,
        reload=True,
    )
