"""Orchestrator: LangGraph StateGraph wiring Planner and Executor with optional re-planning."""
import asyncio
import base64
import logging
from datetime import datetime
from typing import Callable, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from browser.controller import BrowserController
from config import settings
from gemini.client import GeminiClient
from models.schemas import (
    BrowserAction,
    ContentReport,
    ExecutionStep,
    GeminiResponse,
    TaskExecution,
    TaskStatus,
)
from utils.stream_manager import browser_stream_manager
from utils.pdf_extractor import extract_text_from_pdf
from utils.youtube_extractor import get_transcript as get_youtube_transcript

from .executor_agent import ExecutorAgent, ExecutorResult
from .planner_agent import PlannerAgent

logger = logging.getLogger(__name__)

MAX_STEPS = 30
MAX_PLAN_ROUNDS = 15
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
    plan_round: int
    _screenshot_bytes: bytes
    reports: list[ContentReport]
    _do_extract: bool


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
    # Get current URL so the planner knows where it is
    current_url = await browser.get_current_url()
    await browser.add_labels()
    screenshot_bytes = await browser.screenshot(**SCREENSHOT_OPTS)
    await browser.remove_labels()
    b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    # Build a summary of steps already done for the planner
    steps_done = [
        f"{s.action.type}: {s.reasoning}"
        for s in (state.get("steps") or [])
    ]

    try:
        plan = await planner.run(
            screenshot_bytes,
            state["task_description"],
            steps_done=steps_done or None,
            current_url=current_url,
        )
    except Exception as plan_err:
        logger.error("[Orchestrator] Planning failed: %s", plan_err)
        return {
            "current_screenshot": b64,
            "plan": None,
            "decision_index": 0,
            "status": "failed",
            "error": f"Planning error: {plan_err}",
        }

    if not plan.decisions:
        # Model returned a summary with no further actions → task is complete
        summary = (plan.summary or "").strip()
        if plan.taskComplete or len(summary) > 10:
            logger.info("[Orchestrator] Task complete — agent returned answer: %s", summary[:120])
            return {
                "current_screenshot": b64,
                "plan": plan.model_dump(),
                "decision_index": 0,
                "status": "completed",
                "final_answer": summary,
            }
        # Genuinely could not plan
        logger.warning("[Orchestrator] No decisions and no meaningful summary — marking failed")
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
        "plan_round": state.get("plan_round", 0) + 1,
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
    # "extract" is handled by EXTRACT node; do not run browser action
    if decision.action.type == "extract":
        logger.info("[Orchestrator] Routing to EXTRACT node (decision %s)", idx + 1)
        return {
            "_do_extract": True,
            "decision_index": idx,
        }

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

    return {
        "steps": steps,
        "current_screenshot": base64.b64encode(exec_result.screenshot_bytes).decode("utf-8"),
        "decision_index": next_index,
        "status": new_status,
        "_screenshot_bytes": exec_result.screenshot_bytes,
    }


async def _node_extract(state: AgentState) -> dict:
    """Detect content type, extract text/transcript, run Vertex AI analysis; set reports and complete."""
    browser = _get_browser()
    gemini = GeminiClient()
    task_description = state.get("task_description") or ""
    page_url = await browser.get_current_url()
    content_type = await browser.detect_content_type()
    content = ""
    if content_type == "youtube":
        content = get_youtube_transcript(page_url)
        if not content:
            content = await browser.get_page_text()
    elif content_type == "pdf":
        pdf_url = await browser.get_pdf_url_from_page()
        if pdf_url:
            pdf_bytes = await browser.download_pdf(pdf_url)
            content = extract_text_from_pdf(pdf_bytes)
        if not content:
            content = await browser.get_page_text()
            content_type = "page"
    else:
        content = await browser.get_page_text()
    # Force QA path when task is a QA scan so client always uses QA prompt and report shape
    _task_lower = (task_description or "").lower()
    if any(kw in _task_lower for kw in ("qa scan", "qa scan on", "quality assurance", "run a qa")):
        content_type = "qa"
    else:
        # Fallback: plan may say "extract ... to analyze for QA" even if task_description was lost
        plan = _get_plan(state)
        if plan and plan.decisions and plan.decisions[0].action.type == "extract":
            summary_lower = (plan.summary or "").lower()
            if "qa" in summary_lower or "quality assurance" in summary_lower:
                content_type = "qa"
    reports: list[ContentReport] = []
    if content.strip():
        await asyncio.sleep(2)  # Throttle before Gemini to reduce 429 rate limits
        reports = await gemini.extract_and_analyze(content, content_type, task_description, page_url)
    else:
        reports = [ContentReport(title="No content", url=page_url, content_type=content_type, content="No text could be extracted.")]
    steps = list(state.get("steps") or [])
    plan = _get_plan(state)
    idx = state.get("decision_index", 0)
    synthetic_step = ExecutionStep(
        stepNumber=len(steps) + 1,
        description="Extract and analyze page content",
        action=BrowserAction(type="extract"),
        screenshot=state.get("current_screenshot") or "",
        beforeScreenshot=state.get("current_screenshot") or "",
        reasoning="Extracted and analyzed content with Vertex AI",
        result=f"Produced {len(reports)} report(s)",
        timestamp=datetime.utcnow(),
    )
    steps.append(synthetic_step)
    plan_dict = state.get("plan")
    decision_index = len(plan.decisions) if plan and plan.decisions else idx + 1

    # Set final_answer so UI and TTS have a human-friendly summary (not raw report text)
    _fallback_msg = "Analysis could not be generated. Please try again or rephrase your query."
    _is_qa_task = content_type == "qa" or any(kw in _task_lower for kw in ("qa scan", "qa scan on", "quality assurance", "run a qa"))
    first_title = (reports[0].title or "").strip() if reports else ""
    if _is_qa_task and reports and (first_title == "No issues found" or first_title == "QA Scan Summary"):
        final_answer = "QA scan complete. You can view the report in the Report tab."
    elif reports and reports[0].content and reports[0].content.strip() != _fallback_msg:
        report_title = reports[0].title or "the page"
        n = len(reports)
        final_answer = (
            f"Analysis of {report_title} is complete. "
            f"I have prepared a detailed report with {n} section(s). "
            "You can view the full report in the Report tab."
        )
    else:
        final_answer = f"Extraction complete. {len(reports)} report(s) generated."

    return {
        "steps": steps,
        "reports": reports,
        "status": "completed",
        "final_answer": final_answer,
        "_do_extract": False,
        "decision_index": decision_index,
    }


def _is_research_task(desc: str) -> bool:
    """True if the task description suggests the user wants a report or analysis."""
    if not desc or not desc.strip():
        return False
    d = desc.lower().strip()
    keywords = (
        "report", "analyze", "summarize", "research", "tell me about",
        "explain", "information about", "details about", "give me a report",
        "search about", "find out about",
        "qa", "qa scan", "quality assurance",
    )
    return any(kw in d for kw in keywords)


def _route_after_plan(state: AgentState) -> Literal["execute_step", "extract", "end"]:
    plan = _get_plan(state)
    if not plan or not plan.decisions:
        logger.info("[Orchestrator] Routing plan -> end (no decisions)")
        return "end"
    if plan.decisions[0].action.type == "extract":
        logger.info("[Orchestrator] First decision is extract -> EXTRACT node")
        return "extract"
    logger.info("[Orchestrator] Routing plan -> execute_step (%s decisions)", len(plan.decisions))
    return "execute_step"


def _route_after_execute(state: AgentState) -> Literal["execute_step", "plan", "extract", "end"]:
    if state.get("cancelled"):
        return "end"
    if state.get("_do_extract"):
        return "extract"
    status = state.get("status")
    if status in ("failed", "cancelled"):
        return "end"
    if status == "completed":
        # Auto-trigger extract when user asked for a report but we completed without one
        reports = state.get("reports") or []
        task_desc = state.get("task_description") or ""
        if not reports and _is_research_task(task_desc):
            logger.info("[Orchestrator] Completed without reports but task is research-style → routing to EXTRACT")
            return "extract"
        return "end"
    # Hard limits
    if len(state.get("steps") or []) >= MAX_STEPS:
        return "end"
    plan = _get_plan(state)
    idx = state.get("decision_index", 0)
    # Still have decisions left in the current plan — keep executing
    if plan and plan.decisions and idx < len(plan.decisions):
        return "execute_step"
    # All decisions done but task not complete — re-plan from new screenshot
    if state.get("plan_round", 0) < MAX_PLAN_ROUNDS:
        return "plan"
    return "end"


def build_agent_graph():
    """Build and compile the LangGraph StateGraph."""
    builder = StateGraph(AgentState)

    builder.add_node("navigate", _node_navigate)
    builder.add_node("plan", _node_plan)
    builder.add_node("execute_step", _node_execute_step)
    builder.add_node("extract", _node_extract)

    builder.add_edge(START, "navigate")
    builder.add_edge("navigate", "plan")
    builder.add_conditional_edges(
        "plan",
        _route_after_plan,
        {"execute_step": "execute_step", "extract": "extract", "end": END},
    )
    builder.add_conditional_edges(
        "execute_step",
        _route_after_execute,
        {"execute_step": "execute_step", "plan": "plan", "extract": "extract", "end": END},
    )
    builder.add_edge("extract", END)

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
        "plan_round": 0,
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

    step_counter = 0
    async for event in graph.astream(initial):
        for node_name, node_state in event.items():
            # Merge node output into our task view
            if "steps" in node_state:
                task.steps = node_state["steps"]
                step_counter = len(task.steps)
            if "current_screenshot" in node_state:
                task.currentScreenshot = node_state["current_screenshot"]
                # Push live frame to any connected WebSocket client immediately
                asyncio.ensure_future(
                    browser_stream_manager.push_frame(
                        task_id,
                        node_state["current_screenshot"],
                        step=step_counter,
                    )
                )
            if "status" in node_state:
                task.status = node_state["status"]
            if "error" in node_state:
                task.error = node_state["error"]
            if "start_url" in node_state:
                task.startUrl = node_state["start_url"]
            if "final_answer" in node_state and node_state["final_answer"]:
                task.finalAnswer = node_state["final_answer"]
            if "reports" in node_state:
                task.reports = node_state["reports"]
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
