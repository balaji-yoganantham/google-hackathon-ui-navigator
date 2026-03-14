"""Async task queue: process one task at a time, enqueue by session_id."""
import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class TaskQueue:
    """Single-worker queue: process items one by one. Item id = session_id."""

    def __init__(self, processor: Callable[[str, Any], Awaitable[None]]) -> None:
        self._processor = processor
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._current_id: Optional[str] = None
        self._worker_started = False

    def _ensure_worker(self) -> None:
        if self._worker_started:
            return
        self._worker_started = True
        asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        while True:
            try:
                session_id, payload = await self._queue.get()
                self._current_id = session_id
                try:
                    await self._processor(session_id, payload)
                except Exception as e:
                    logger.exception("Task queue processor failed for %s: %s", session_id, e)
                finally:
                    self._current_id = None
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Task queue worker error: %s", e)

    def enqueue(self, session_id: str, payload: Any) -> None:
        self._ensure_worker()
        self._queue.put_nowait((session_id, payload))

    def cancel(self, session_id: str) -> bool:
        """Remove one matching item from the queue (if present). Returns True if removed."""
        # asyncio.Queue doesn't support remove; we'd need a different structure.
        # For simplicity we don't remove from queue; only "cancel" affects running task.
        return False

    def get_current_session_id(self) -> Optional[str]:
        return self._current_id

    def get_queue_length(self) -> int:
        return self._queue.qsize()
