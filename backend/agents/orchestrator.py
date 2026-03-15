"""Orchestrator: LangGraph StateGraph wiring Planner and Executor with optional re-planning."""
import base64
import logging
from datetime import datetime
from typing import Callable, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from browser.controller import BrowserController
from config import settings
from gemini.client import GeminiClient
from models.schemas import (
    ExecutionStep,
    GeminiResponse,
    TaskExecution,
    TaskStatus,
)

from .executor_agent import ExecutorAgent, ExecutorResult
from .planner_agent import PlannerAgent

logger = logging.getLogger(__name__)

MAX_STEPS = 10
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

    plan = await planner.run(screenshot_bytes, state["task_description"])
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
        "current_screenshot": b64,
        "plan": plan.model_dump(),
        "decision_index": 0,
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
        beforeScreenshot=base64.b64encode(exec_result.before_screenshot_bytes).decode("utf-8"),
        reasoning=decision.reasoning,
        result=exec_result.result,
        timestamp=datetime.utcnow(),
    )
    steps = list(state.get("steps") or [])
    steps.append(step)
    next_index = idx + 1
    new_status: TaskStatus = state.get("status") or "running"
    if exec_result.outcome == "complete" or task_complete:
        new_status = "completed"
    elif not exec_result.success and settings.SINGLE_MODEL_REQUEST_MODE:
        # In single-mode we don't replan; continue and mark failed at end if needed
        pass
    elif not exec_result.success:
        new_status = "failed"
        # Could route to plan for replan; for simplicity we stop on first failure here
    if next_index >= len(plan.decisions):
        if new_status == "running":
            new_status = "completed"

    return {
        "steps": steps,
        "current_screenshot": base64.b64encode(exec_result.screenshot_bytes).decode("utf-8"),
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


def _route_after_execute(state: AgentState) -> Literal["execute_step", "plan", "end"]:
    if state.get("cancelled"):
        return "end"
    if state.get("status") in ("completed", "failed", "cancelled"):
        return "end"
    plan = _get_plan(state)
    idx = state.get("decision_index", 0)
    if not plan or not plan.decisions or idx >= len(plan.decisions):
        return "end"
    if not settings.SINGLE_MODEL_REQUEST_MODE and state.get("error"):
        return "plan"
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
        if task.status in ("completed", "failed", "cancelled"):
            logger.info("[Orchestrator] Task %s finished: status=%s steps=%s", task_id, task.status, len(task.steps))
            return task

    task.updatedAt = datetime.utcnow()
    logger.info("[Orchestrator] Task %s ended: status=%s steps=%s", task_id, task.status, len(task.steps))
    return task
