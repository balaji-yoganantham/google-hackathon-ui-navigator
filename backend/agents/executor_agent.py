"""Executor Agent: executes one browser action, captures result and new screenshot."""
import logging
from dataclasses import dataclass
from typing import Literal

from browser.controller import BrowserController
from models.schemas import AgentDecision, BrowserAction

logger = logging.getLogger(__name__)

Outcome = Literal["continue", "replan", "complete"]


@dataclass
class ExecutorResult:
    """Result of executing one action."""
    result: str
    screenshot_bytes: bytes
    success: bool
    outcome: Outcome  # continue to next step, replan, or task complete


class ExecutorAgent:
    """Executes a single browser action and returns result + new screenshot."""

    def __init__(self, browser_controller: BrowserController | None = None) -> None:
        self._browser = browser_controller or BrowserController()

    async def run(
        self,
        decision: AgentDecision,
        task_complete: bool,
        screenshot_options: dict | None = None,
    ) -> ExecutorResult:
        """
        Execute one action from a planner decision.
        outcome: "complete" if task_complete, "replan" if action failed, else "continue".
        """
        action = decision.action
        opts = screenshot_options or {"quality": 60, "clip_to_viewport": True}
        logger.info("[ExecutorAgent] Executing action: type=%s selector=%s", action.type, getattr(action, "selector", None))

        # Re-add wayfinder labels so [data-wayfinder-id='N'] selectors exist at execution time
        await self._browser.add_labels()

        try:
            result_msg = await self._browser.execute_action(action)
            logger.info("[ExecutorAgent] Action succeeded: %s", result_msg)
        except Exception as e:
            logger.warning("[ExecutorAgent] Action failed: %s", e)
            # Remove labels and take screenshot of failure state
            try:
                await self._browser.remove_labels()
                screenshot_bytes = await self._browser.screenshot(**opts)
            except Exception:
                screenshot_bytes = b""
            return ExecutorResult(
                result=f"Failed: {e}",
                screenshot_bytes=screenshot_bytes,
                success=False,
                outcome="replan",
            )

        # After actions that often cause navigation, wait for the new page to load before remove_labels/screenshot
        if action.type in ("press", "click", "navigate"):
            await self._browser.wait_for_load_after_navigation(timeout_ms=12_000)

        # Smart wait by action type
        if action.type in ("click", "navigate"):
            await self._browser.smart_wait(800)
        elif action.type in ("type", "press"):
            await self._browser.smart_wait(400)
        elif action.type == "scroll":
            await self._browser.smart_wait(300)

        # Remove labels so the stored screenshot is clean (no red numbers)
        await self._browser.remove_labels()
        screenshot_bytes = await self._browser.screenshot(**opts)
        outcome: Outcome = "complete" if task_complete else "continue"
        return ExecutorResult(
            result=result_msg,
            screenshot_bytes=screenshot_bytes,
            success=True,
            outcome=outcome,
        )
