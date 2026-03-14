"""Planner Agent: screenshot + task description → structured action plan via Gemini."""
import logging
from typing import Optional

from gemini.client import GeminiClient
from models.schemas import GeminiResponse

logger = logging.getLogger(__name__)


class PlannerAgent:
    """LangChain-style planner: takes screenshot and task, returns GeminiResponse (action plan)."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self._client = gemini_client or GeminiClient()

    async def run(self, screenshot_bytes: bytes, task_description: str) -> GeminiResponse:
        """Produce a full action plan from one screenshot and the user task."""
        logger.info("[PlannerAgent] Planning task: %s", task_description[:80])
        plan = await self._client.plan_task(screenshot_bytes, task_description)
        logger.info(
            "[PlannerAgent] Plan: %s decisions, summary=%s",
            len(plan.decisions),
            plan.summary[:60] if plan.summary else "",
        )
        return plan
