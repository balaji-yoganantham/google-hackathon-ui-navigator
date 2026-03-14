"""In-memory session store for task state (SSE/polling)."""
import logging
from typing import Optional

from models.schemas import TaskExecution

logger = logging.getLogger(__name__)


class SessionManager:
    """Thread-safe in-memory store: session_id -> (TaskExecution, owner_uid?)."""

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[TaskExecution, Optional[str]]] = {}
        self._lock = None  # optional asyncio.Lock if needed

    def create_session(
        self,
        session_id: str,
        task: TaskExecution,
        owner_uid: Optional[str] = None,
    ) -> None:
        self._sessions[session_id] = (task, owner_uid)

    def get_session(self, session_id: str) -> Optional[TaskExecution]:
        entry = self._sessions.get(session_id)
        if not entry:
            return None
        return entry[0]

    def get_session_entry(
        self, session_id: str
    ) -> Optional[tuple[TaskExecution, Optional[str]]]:
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, task: TaskExecution) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = (task, None)
        else:
            _, uid = self._sessions[session_id]
            self._sessions[session_id] = (task, uid)

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_session_ids(self) -> list[str]:
        return list(self._sessions.keys())


session_manager = SessionManager()
