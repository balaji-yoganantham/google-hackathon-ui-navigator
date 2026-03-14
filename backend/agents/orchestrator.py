"""Orchestrator: LangGraph StateGraph wiring Planner and Executor with optional re-planning."""
import base64
import logging
from datetime import datetime
from typing import Callable, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from browser.controller import BrowserController
from config import settings
from gemini.client import GeminiClient
from utils.browser_pool import browser_pool
from models.schemas import (
    ExecutionStep,
    GeminiResponse,
    TaskExecution,
    TaskStatus,
)

from .executor_agent import ExecutorAgent, ExecutorResult
from .planner_agent import PlannerAgent

logger = logging.getLogger(__name__)

MAX_STEPS = 20   # Raised to handle multi-step tasks (e.g. iterate through job listings)
MAX_REPLANS = 3  # Maximum re-plans triggered by step failures (e.g. mid-task pop-ups)
SCREENSHOT_OPTS = {"quality": 60, "clip_to_viewport": True}


class AgentState(TypedDict, total=False):
    """State for the agent graph (plan stored as dict for serialization)."""
    task_id: str
    task_description: str
    start_url: str
    steps: list[ExecutionStep]
    current_screenshot: str
    plan: dict | None  # GeminiResponse as dict
    decision_index: int
    status: TaskStatus
    error: str | None
    replan_count: int   # Number of re-plans triggered by failures so far
    cancelled: bool
    _screenshot_bytes: bytes


def _get_browser() -> BrowserController:
    return BrowserController()


def _get_planner() -> PlannerAgent:
    return PlannerAgent()


def _get_executor() -> ExecutorAgent:
    return ExecutorAgent(browser_controller=_get_browser())


async def _node_navigate(state: AgentState) -> dict:
    """Resolve start URL from task (if not provided), then navigate and wait."""
    browser = _get_browser()
    start_url = state.get("start_url") or ""
    if not start_url:
        resolved = await GeminiClient().resolve_start_url(state["task_description"])
        start_url = resolved
        logger.info("[Orchestrator] Resolved start URL: %s", start_url)
    await browser.navigate_to_url(start_url)
    await browser.smart_wait(800)
    return {"status": "running", "start_url": start_url}


async def _node_plan(state: AgentState) -> dict:
    """Add labels, screenshot, call planner; set plan and decision_index."""
    browser = _get_browser()
    planner = _get_planner()
    await browser.add_labels()
    screenshot_bytes = await browser.screenshot(**SCREENSHOT_OPTS)
    await browser.remove_labels()
    b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    task_description = state["task_description"]

    # Inject the live browser URL so the planner knows where it already is and
    # won't plan a redundant navigate step to the same page.
    try:
        page = await browser_pool.get_page()
        current_url = page.url
        if current_url and current_url not in ("about:blank", ""):
            task_description = f"{task_description}\n\n[Current URL: {current_url}]"
    except Exception:
        pass  # Non-fatal — planner still works without URL hint

    replan_count = state.get("replan_count", 0)

    # Routing here from a "completed" state means we're replanning after the agent
    # reported done but the safeguard found the task incomplete (dismiss-only or
    # unmet requirements). Bump replan_count and reset status so we don't loop forever.
    replan_after_completion = state.get("status") == "completed"
    extra_state: dict = {}
    if replan_after_completion:
        extra_state = {"replan_count": replan_count + 1, "status": "running"}
        logger.info(
            "[Orchestrator] Replan after completion — status=running, replan_count=%s/%s",
            replan_count + 1,
            MAX_REPLANS,
        )

    # When re-planning after a failure, inject failure context so the model
    # knows to look for pop-ups / overlays that caused the previous step to fail.
    if state.get("error") and replan_count > 0:
        task_description = (
            f"{task_description}\n\n"
            f"[Re-planning attempt {replan_count}/{MAX_REPLANS}: "
            f"A previous step failed — {state['error']}. "
            f"Carefully inspect the current screenshot for any pop-ups, modals, "
            f"cookie banners, or overlays blocking the page and dismiss them first "
            f"before retrying the main task.]"
        )
        logger.info("[Orchestrator] Re-planning with failure context (attempt %s/%s)", replan_count, MAX_REPLANS)
    elif replan_after_completion:
        task_description = (
            f"{task_description}\n\n"
            f"[The previous plan only completed PART of the task. The page is now in a new state. "
            f"Look at the current screenshot and plan ALL REMAINING steps of the original task. "
            f"Do NOT repeat steps that are already done. "
            f"Include every outstanding requirement: filtering, finding specific items, checking prices, saving, etc.]"
        )

    try:
        plan = await planner.run(screenshot_bytes, task_description)
    except ValueError as e:
        logger.warning("[Orchestrator] Planner failed (e.g. empty model response): %s", str(e)[:120])
        return {
            **extra_state,
            "current_screenshot": b64,
            "plan": None,
            "decision_index": 0,
            "status": "failed",
            "error": str(e)[:200] or "AI could not create a plan for this task",
        }
    if not plan.decisions:
        return {
            "current_screenshot": b64,
            "plan": None,
            "decision_index": 0,
            "status": "failed",
            "error": "AI could not create a plan for this task",
        }
    logger.info("[Orchestrator] Plan: %s decisions", len(plan.decisions))
    return {
        **extra_state,
        "current_screenshot": b64,
        "plan": plan.model_dump(),
        "decision_index": 0,
        "error": None,  # Clear failure context once a new plan is ready
        "_screenshot_bytes": screenshot_bytes,
    }


def _get_plan(state: AgentState) -> GeminiResponse | None:
    raw = state.get("plan")
    if not raw:
        return None
    if isinstance(raw, GeminiResponse):
        return raw
    return GeminiResponse.model_validate(raw)


async def _node_execute_step(state: AgentState) -> dict:
    """Execute one decision; append step; update screenshot; set next index or status."""
    if state.get("cancelled"):
        return {"status": "cancelled"}
    plan = _get_plan(state)
    if not plan or not plan.decisions:
        logger.info("[Orchestrator] Execute step skipped: no plan or no decisions")
        return {"status": "completed"}
    idx = state.get("decision_index", 0)
    if idx >= len(plan.decisions):
        logger.info("[Orchestrator] Execute step skipped: index %s >= %s decisions", idx, len(plan.decisions))
        return {"status": "completed"}
    if len(state.get("steps") or []) >= MAX_STEPS:
        logger.info("[Orchestrator] Execute step skipped: max steps %s reached", MAX_STEPS)
        return {"status": "completed"}

    decision = plan.decisions[idx]
    logger.info("[Orchestrator] Executing step %s/%s: %s", idx + 1, len(plan.decisions), decision.action.type)
    executor = _get_executor()
    task_complete = plan.taskComplete and idx == len(plan.decisions) - 1
    exec_result: ExecutorResult = await executor.run(
        decision, task_complete=task_complete, screenshot_options=SCREENSHOT_OPTS
    )

    step = ExecutionStep(
        stepNumber=len(state.get("steps") or []) + 1,
        description=decision.reasoning,
        action=decision.action,
        screenshot=base64.b64encode(exec_result.screenshot_bytes).decode("utf-8"),
        reasoning=decision.reasoning,
        result=exec_result.result,
        timestamp=datetime.utcnow(),
    )
    steps = list(state.get("steps") or [])
    steps.append(step)
    b64_screenshot = base64.b64encode(exec_result.screenshot_bytes).decode("utf-8")

    if exec_result.outcome == "complete" or task_complete:
        # Safeguard: if the first plan only dismissed a pop-up/overlay, force a replan
        # so the actual task still runs.
        # Uses keyword matching on the plan summary/reasoning — avoids fragile attribute
        # access on step objects that LangGraph may have serialised to plain dicts.
        replan_count = state.get("replan_count", 0)
        if replan_count == 0 and len(plan.decisions) <= 2:
            _DISMISS_KEYWORDS = (
                "pop", "modal", "overlay", "dismiss", "close",
                "sign-in", "signin", "banner", "dialog", "popup",
            )
            summary_lower = (plan.summary or "").lower()
            reasoning_lower = (decision.reasoning or "").lower()
            is_dismiss_only = any(
                kw in summary_lower or kw in reasoning_lower
                for kw in _DISMISS_KEYWORDS
            )
            if is_dismiss_only:
                logger.info(
                    "[Orchestrator] Dismiss-only plan on first run (summary: %s) — "
                    "triggering replan to execute main task.",
                    plan.summary[:80],
                )
                return {
                    "steps": steps,
                    "current_screenshot": b64_screenshot,
                    "decision_index": idx + 1,
                    "status": "running",
                    "error": "Pop-up/overlay dismissed — re-planning to continue the main task.",
                    "replan_count": 1,
                    "_screenshot_bytes": exec_result.screenshot_bytes,
                }
        return {
            "steps": steps,
            "current_screenshot": b64_screenshot,
            "decision_index": idx + 1,
            "status": "completed",
            "_screenshot_bytes": exec_result.screenshot_bytes,
        }

    if not exec_result.success:
        replan_count = state.get("replan_count", 0)
        if replan_count < MAX_REPLANS:
            # Trigger a re-plan: take a fresh screenshot so the planner can see
            # any pop-up or overlay that caused this step to fail.
            failure_msg = f"Step {idx + 1} ({decision.action.type}) failed — {exec_result.result}"
            logger.info(
                "[Orchestrator] %s — scheduling replan (%s/%s)",
                failure_msg, replan_count + 1, MAX_REPLANS,
            )
            return {
                "steps": steps,
                "current_screenshot": b64_screenshot,
                "decision_index": idx + 1,
                "status": "running",
                "error": failure_msg,
                "replan_count": replan_count + 1,
                "_screenshot_bytes": exec_result.screenshot_bytes,
            }
        # Replan budget exhausted — mark as failed
        logger.info("[Orchestrator] Step failed and replan budget exhausted (%s/%s)", replan_count, MAX_REPLANS)
        return {
            "steps": steps,
            "current_screenshot": b64_screenshot,
            "decision_index": idx + 1,
            "status": "failed",
            "_screenshot_bytes": exec_result.screenshot_bytes,
        }

    # Step succeeded — continue to next step or complete
    next_index = idx + 1
    new_status: TaskStatus = "completed" if next_index >= len(plan.decisions) else "running"
    return {
        "steps": steps,
        "current_screenshot": b64_screenshot,
        "decision_index": next_index,
        "status": new_status,
        "_screenshot_bytes": exec_result.screenshot_bytes,
    }


def _route_after_plan(state: AgentState) -> Literal["execute_step", "end"]:
    plan = _get_plan(state)
    if plan and (plan.decisions or []):
        logger.info("[Orchestrator] Routing plan -> execute_step (%s decisions)", len(plan.decisions))
        return "execute_step"
    logger.info("[Orchestrator] Routing plan -> end (no decisions)")
    return "end"


_DISMISS_KEYWORDS = (
    "pop", "modal", "overlay", "dismiss", "close",
    "sign-in", "signin", "sign in",
    "banner", "dialog", "popup",
)

# Task keywords that signal a multi-requirement task.  If ANY of these appear
# in the task description but NOT in what the plan actually covered, the task
# has unmet requirements and needs a replan.
_TASK_REQUIREMENT_KEYWORDS = (
    "filter", "4 star", "rating", "badge", "deal", "limited time",
    "price", "save", "bookmark", "find the", "sort by",
    "password", "username",
)


def _route_after_execute(state: AgentState) -> Literal["execute_step", "plan", "end"]:
    if state.get("cancelled"):
        return "end"

    status = state.get("status")

    # Error-based replan (step failure or explicit replan trigger).
    if state.get("error") and status == "running":
        return "plan"

    if status in ("failed", "cancelled"):
        return "end"

    if status == "completed":
        replan_count = state.get("replan_count", 0)
        steps = state.get("steps") or []
        plan = _get_plan(state)

        if plan and replan_count < MAX_REPLANS:
            plan_text = (
                f"{plan.summary or ''} "
                + " ".join(d.reasoning for d in (plan.decisions or []))
            ).lower()

            # Safeguard A: dismiss-only (pop-up/modal dismissed, actual task not started).
            # Only on first completion to avoid false positives.
            if replan_count == 0 and len(steps) <= 2 and any(
                kw in plan_text for kw in _DISMISS_KEYWORDS
            ):
                logger.info(
                    "[Orchestrator] Dismiss-only completion (steps=%s, summary=%s) — routing to replan.",
                    len(steps),
                    (plan.summary or "")[:80],
                )
                return "plan"

            # Safeguard B: task has unmet requirements. Run on every completion
            # until replan budget is exhausted so we keep replanning until the
            # full task is done (e.g. filter + find deal + price).
            task_desc_lower = (state.get("task_description") or "").lower()
            unmet = [
                kw for kw in _TASK_REQUIREMENT_KEYWORDS
                if kw in task_desc_lower and kw not in plan_text
            ]
            if unmet:
                logger.info(
                    "[Orchestrator] Task has unmet requirements %s (replan %s/%s) — routing to replan.",
                    unmet,
                    replan_count + 1,
                    MAX_REPLANS,
                )
                return "plan"

        return "end"

    plan = _get_plan(state)
    idx = state.get("decision_index", 0)
    if not plan or not plan.decisions or idx >= len(plan.decisions):
        return "end"
    return "execute_step"


def build_agent_graph():
    """Build and compile the LangGraph StateGraph."""
    builder = StateGraph(AgentState)

    builder.add_node("navigate", _node_navigate)
    builder.add_node("plan", _node_plan)
    builder.add_node("execute_step", _node_execute_step)

    builder.add_edge(START, "navigate")
    builder.add_edge("navigate", "plan")
    builder.add_conditional_edges("plan", _route_after_plan, {"execute_step": "execute_step", "end": END})
    builder.add_conditional_edges(
        "execute_step",
        _route_after_execute,
        {"execute_step": "execute_step", "plan": "plan", "end": END},
    )

    return builder.compile()


async def run_task(
    task_id: str,
    task_description: str,
    start_url: str = "",
    *,
    on_update: Optional[Callable[[TaskExecution], None]] = None,
    get_cancelled: Optional[Callable[[], bool]] = None,
) -> TaskExecution:
    """
    Run the full agent loop and return the final TaskExecution.
    on_update: optional callback called after each step (for SSE).
    get_cancelled: optional callback that returns True to stop the run.
    """
    initial: AgentState = {
        "task_id": task_id,
        "task_description": task_description,
        "start_url": start_url or "",
        "steps": [],
        "current_screenshot": "",
        "plan": None,
        "decision_index": 0,
        "status": "running",
        "error": None,
        "replan_count": 0,
        "cancelled": False,
    }

    graph = build_agent_graph()
    task = TaskExecution(
        id=task_id,
        taskDescription=task_description,
        status="running",
        steps=[],
        currentScreenshot=initial["current_screenshot"],
        startUrl=start_url,
        createdAt=datetime.utcnow(),
        updatedAt=datetime.utcnow(),
    )

    def _emit():
        if on_update:
            task.updatedAt = datetime.utcnow()
            on_update(task)

    async for event in graph.astream(initial):
        for node_name, node_state in event.items():
            # Merge node output into our task view
            if "steps" in node_state:
                task.steps = node_state["steps"]
            if "current_screenshot" in node_state:
                task.currentScreenshot = node_state["current_screenshot"]
            if "status" in node_state:
                task.status = node_state["status"]
            if "error" in node_state:
                task.error = node_state["error"]
            if "start_url" in node_state:
                task.startUrl = node_state["start_url"]
        _emit()
        if get_cancelled and get_cancelled():
            task.status = "cancelled"
            _emit()
            logger.info("[Orchestrator] Task %s cancelled", task_id)
            return task
        # Only hard-stop for terminal error/cancel states.
        # "completed" is intentionally excluded — the graph may still route to a
        # replan node (e.g. after a dismiss-only first plan) before truly finishing.
        if task.status in ("failed", "cancelled"):
            logger.info("[Orchestrator] Task %s stopped: status=%s steps=%s", task_id, task.status, len(task.steps))
            return task

    task.updatedAt = datetime.utcnow()
    logger.info("[Orchestrator] Task %s finished: status=%s steps=%s", task_id, task.status, len(task.steps))
    return task
