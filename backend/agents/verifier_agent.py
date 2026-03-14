"""Verifier Agent: screenshot + task + steps summary → completion check via Gemini."""
import logging
from typing import Optional

from gemini.client import GeminiClient
from models.schemas import VerifierResponse

logger = logging.getLogger(__name__)


class VerifierAgent:
    """Checks whether the original task is complete given current screenshot and executed steps."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self._client = gemini_client or GeminiClient()

    async def run(
        self,
        screenshot_bytes: bytes,
        task_description: str,
        steps_summary: str,
    ) -> VerifierResponse:
        """Verify task completion: returns task_complete, reasoning, remaining_requirements."""
        logger.info("[VerifierAgent] Verifying progress for task: %s", task_description[:60])
        result = await self._client.verify_progress(
            screenshot_bytes, task_description, steps_summary
        )
        logger.info(
            "[VerifierAgent] task_complete=%s, remaining=%s",
            result.task_complete,
            result.remaining_requirements[:3] if result.remaining_requirements else [],
        )
        return result
