"""WebSocket browser stream manager — one live connection per session."""
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


class BrowserStreamManager:
    """
    Singleton registry of active WebSocket connections keyed by session_id.

    The executor pushes JPEG frames here via push_frame(); the WebSocket
    endpoint registers/unregisters clients via connect/disconnect.
    """

    def __init__(self) -> None:
        self._sockets: dict[str, "WebSocket"] = {}

    def connect(self, session_id: str, ws: "WebSocket") -> None:
        self._sockets[session_id] = ws
        logger.info("[StreamManager] session %s connected", session_id)

    def disconnect(self, session_id: str) -> None:
        self._sockets.pop(session_id, None)
        logger.info("[StreamManager] session %s disconnected", session_id)

    async def push_frame(self, session_id: str, screenshot_b64: str, step: int = 0) -> None:
        """Send a JPEG frame (base64) to the client watching this session."""
        ws = self._sockets.get(session_id)
        if not ws:
            return
        try:
            await ws.send_text(
                json.dumps({"type": "screenshot", "screenshot": screenshot_b64, "step": step})
            )
        except Exception as exc:
            logger.debug("[StreamManager] push_frame failed for %s: %s", session_id, exc)
            self.disconnect(session_id)

    def is_connected(self, session_id: str) -> bool:
        return session_id in self._sockets


browser_stream_manager = BrowserStreamManager()
