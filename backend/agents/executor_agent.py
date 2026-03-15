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
    """Result of executing one action (before + after screenshots)."""
    result: str
    screenshot_bytes: bytes  # after action
    before_screenshot_bytes: bytes  # before action
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
        # Capture before-action screenshot (clean, no labels)
        await self._browser.remove_labels()
        before_screenshot_bytes = await self._browser.screenshot(**opts)
        await self._browser.add_labels()

        try:
            result_msg = await self._browser.execute_action(action)
            logger.info("[ExecutorAgent] Action succeeded: %s", result_msg)
        except Exception as e:
            logger.warning("[ExecutorAgent] Action failed: %s", e)
            try:
                await self._browser.remove_labels()
                after_screenshot_bytes = await self._browser.screenshot(**opts)
            except Exception:
                after_screenshot_bytes = b""
            return ExecutorResult(
                result=f"Failed: {e}",
                screenshot_bytes=after_screenshot_bytes,
                before_screenshot_bytes=before_screenshot_bytes,
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

        # For click actions, re-apply labels AFTER the wait so that any dynamic content
        # opened by the click (dropdowns, modals, autocomplete lists) gets numbered.
        # This means the after-screenshot will show labeled new content for debugging,
        # and _node_plan will also see labeled dynamic content when it re-labels for re-planning.
        if action.type == "click":
            try:
                await self._browser.add_labels()
                logger.debug("[ExecutorAgent] Re-labeled page after click action")
            except Exception as label_err:
                logger.debug("[ExecutorAgent] Re-label after click skipped: %s", label_err)

        # Remove labels so the stored after-screenshot is clean (no red numbers)
        await self._browser.remove_labels()
        after_screenshot_bytes = await self._browser.screenshot(**opts)
        outcome: Outcome = "complete" if task_complete else "continue"
        return ExecutorResult(
            result=result_msg,
            screenshot_bytes=after_screenshot_bytes,
            before_screenshot_bytes=before_screenshot_bytes,
            success=True,
            outcome=outcome,
        )
