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
from .verifier_agent import VerifierAgent

logger = logging.getLogger(__name__)

MAX_STEPS = 20   # Raised to handle multi-step tasks (e.g. iterate through job listings)
MAX_REPLANS = 6  # Re-plans until task is done or budget exhausted (filter + find + price need several rounds)
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
    verification_result: dict | None  # VerifierResponse as dict
    _screenshot_bytes: bytes


def _get_browser() -> BrowserController:
    return BrowserController()


def _get_planner() -> PlannerAgent:
    return PlannerAgent()


def _get_executor() -> ExecutorAgent:
    return ExecutorAgent(browser_controller=_get_browser())


def _get_verifier() -> VerifierAgent:
    return VerifierAgent()


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
    remaining: list[str] = []
    min_required = 0

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

    # Highest-priority steering: use verifier feedback to force concrete progress.
    verification = state.get("verification_result") or {}
    verifier_remaining_raw = verification.get("remaining_requirements", [])
    verifier_remaining = [
        str(r).strip()
        for r in verifier_remaining_raw
        if isinstance(r, str) and str(r).strip()
    ]
    if verifier_remaining:
        prioritized = verifier_remaining[:4]
        min_required = max(2, min(len(prioritized), 4))
        remaining_str = "; ".join(prioritized)
        task_short = (task_description or "")[:420].strip()
        if len(task_description or "") > 420:
            task_short += "..."
        task_description = (
            f"{task_short}\n\n"
            f"[REMAINING REQUIREMENTS: {remaining_str}. "
            f"Return {min_required}-4 concrete decisions that directly progress these requirements. "
            f"Use click/type/press actions when possible; do not return dismiss-only or scroll-only plans "
            f"unless an overlay is visibly blocking the page. Return valid JSON only.]"
        )
        remaining = prioritized
        logger.info(
            "[Orchestrator] Re-planning with verifier requirements (%s): %s",
            min_required,
            remaining_str[:120],
        )
    # When re-planning after a failure, inject failure context so the model
    # knows to look for pop-ups / overlays that caused the previous step to fail.
    elif state.get("error") and replan_count > 0:
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
        # Requirement checklist: compute which task requirements are still unmet so the
        # model cannot ignore them. Force minimum steps = len(remaining).
        prev_plan = _get_plan(state)
        task_desc_lower = (state.get("task_description") or "").lower()
        if prev_plan:
            plan_text = (
                f"{prev_plan.summary or ''} "
                + " ".join(d.reasoning for d in (prev_plan.decisions or []))
            ).lower()
            # Also include all executed steps so we don't re-flag already-done requirements
            prior_steps = state.get("steps") or []
            steps_text = " ".join(
                (s.get("description", "") + " " + s.get("reasoning", "") + " " + s.get("result", ""))
                if isinstance(s, dict)
                else (getattr(s, "description", "") + " " + getattr(s, "reasoning", "") + " " + getattr(s, "result", ""))
                for s in prior_steps
            ).lower()
            covered_text = plan_text + " " + steps_text
            remaining = [
                kw for kw in _TASK_REQUIREMENT_KEYWORDS
                if kw in task_desc_lower and kw not in covered_text
            ]
        if remaining:
            min_required = max(1, min(len(remaining), 4))
            remaining_str = ", ".join(remaining)
            # Keep prompt short to avoid model empty/malformed responses (token limit, overflow)
            task_short = (task_description or "")[:380].strip()
            if len(task_description or "") > 380:
                task_short += "..."
            task_description = (
                f"{task_short}\n\n"
                f"[Remaining: {remaining_str}. Plan at least {min_required} step(s) — one per requirement. "
                f"Look at the screenshot and return valid JSON with 'decisions' array.]"
            )
        else:
            task_short = (task_description or "")[:380].strip()
            if len(task_description or "") > 380:
                task_short += "..."
            task_description = (
                f"{task_short}\n\n"
                f"[Previous plan did only part of the task. From the screenshot, plan the remaining steps. Return valid JSON.]"
            )

    try:
        plan = await planner.run(screenshot_bytes, task_description)
    except ValueError as e:
        # Retry once with a shorter prompt to avoid empty/malformed responses from long prompts
        logger.warning("[Orchestrator] Planner failed, retrying with shorter prompt: %s", str(e)[:80])
        short_task = (state.get("task_description") or "")[:220].strip()
        if len(state.get("task_description") or "") > 220:
            short_task += "..."
        fallback_prompt = (
            f"{short_task}\n\n"
            f"[Current page in screenshot. Plan the next 2-4 actions to continue. Return valid JSON only: decisions, summary, taskComplete.]"
        )
        try:
            plan = await planner.run(screenshot_bytes, fallback_prompt)
        except ValueError as e2:
            logger.warning("[Orchestrator] Planner retry also failed: %s", str(e2)[:120])
            return {
                **extra_state,
                "current_screenshot": b64,
                "plan": None,
                "decision_index": 0,
                "status": "failed",
                "error": str(e2)[:200] or "AI could not create a plan for this task",
            }
    if not plan.decisions:
        return {
            "current_screenshot": b64,
            "plan": None,
            "decision_index": 0,
            "status": "failed",
            "error": "AI could not create a plan for this task",
        }
    # If we asked for at least N steps (remaining requirements) but got fewer, retry once
    # with a stricter prompt so we don't waste an execute cycle on an invalid 1-step plan.
    if remaining and min_required > 0 and len(plan.decisions) < min_required:
        stricter = (
            f"{task_description}\n\n"
            f"[INVALID: You returned {len(plan.decisions)} decision(s) but there are {min_required} remaining requirements. "
            f"You MUST return at least {min_required} decisions in the 'decisions' array — one step per requirement. "
            f"Try again with the same screenshot.]"
        )
        logger.warning(
            "[Orchestrator] Plan had %s steps but %s remaining requirements — retrying planner once",
            len(plan.decisions),
            min_required,
        )
        try:
            plan_retry = await planner.run(screenshot_bytes, stricter)
            if plan_retry.decisions and len(plan_retry.decisions) >= min_required:
                plan = plan_retry
                logger.info("[Orchestrator] Retry produced %s decisions", len(plan.decisions))
        except Exception:
            pass  # Keep original plan and let safeguard handle it after execution
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


async def _node_verify(state: AgentState) -> dict:
    """Take screenshot, call verifier; return verification_result and status (completed or running)."""
    browser = _get_browser()
    verifier = _get_verifier()
    screenshot_bytes = await browser.screenshot(**SCREENSHOT_OPTS)
    b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    steps = state.get("steps") or []
    steps_summary = "\n".join(
        f"{i + 1}. {s.get('reasoning', '') or s.get('description', '')} -> {s.get('result', '')}"
        if isinstance(s, dict)
        else f"{i + 1}. {getattr(s, 'reasoning', '') or getattr(s, 'description', '')} -> {getattr(s, 'result', '')}"
        for i, s in enumerate(steps)
    )
    task_description = state.get("task_description") or ""

    try:
        result = await verifier.run(screenshot_bytes, task_description, steps_summary or "No steps yet.")
    except Exception as e:
        logger.warning("[Orchestrator] Verifier failed: %s — treating as incomplete, will replan", str(e)[:80])
        result_dict = {"task_complete": False, "reasoning": str(e)[:200], "remaining_requirements": ["verification failed"]}
        replan_count = state.get("replan_count", 0)
        next_replan_count = replan_count + 1
        budget_exhausted = next_replan_count >= MAX_REPLANS
        return {
            "current_screenshot": b64,
            "verification_result": result_dict,
            "status": "failed" if budget_exhausted else "running",
            "error": "Verifier failed and replan budget exhausted." if budget_exhausted else None,
            "replan_count": next_replan_count,
            "_screenshot_bytes": screenshot_bytes,
        }

    result_dict = result.model_dump()
    status: TaskStatus = "completed" if result.task_complete else "running"
    replan_count = state.get("replan_count", 0)
    out: dict = {
        "current_screenshot": b64,
        "verification_result": result_dict,
        "status": status,
        "_screenshot_bytes": screenshot_bytes,
    }
    if not result.task_complete:
        next_replan_count = replan_count + 1
        if next_replan_count >= MAX_REPLANS:
            out["status"] = "failed"
            out["error"] = "Task incomplete after maximum replan attempts."
        out["replan_count"] = next_replan_count
    return out


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
    "price", "save", "bookmark", "sort by",
    "password", "username",
)


def _route_after_verify(state: AgentState) -> Literal["plan", "end"]:
    """After verify: end if task complete or replan budget exhausted; else replan."""
    if state.get("cancelled"):
        return "end"
    replan_count = state.get("replan_count", 0)
    verification = state.get("verification_result") or {}
    task_complete = verification.get("task_complete", False)
    if task_complete:
        logger.info("[Orchestrator] Verifier: task complete — end")
        return "end"
    if replan_count >= MAX_REPLANS:
        logger.info("[Orchestrator] Verifier: replan budget exhausted (%s) — end", replan_count)
        return "end"
    logger.info("[Orchestrator] Verifier: incomplete (replan %s/%s) — routing to plan", replan_count, MAX_REPLANS)
    return "plan"


def _route_after_execute(state: AgentState) -> Literal["execute_step", "plan", "verify", "end"]:
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

        # Safeguard A: dismiss-only (pop-up/modal dismissed, actual task not started).
        if plan and replan_count < MAX_REPLANS:
            plan_text = (
                f"{plan.summary or ''} "
                + " ".join(d.reasoning for d in (plan.decisions or []))
            ).lower()
            if replan_count == 0 and len(steps) <= 2 and any(
                kw in plan_text for kw in _DISMISS_KEYWORDS
            ):
                logger.info(
                    "[Orchestrator] Dismiss-only completion (steps=%s, summary=%s) — routing to replan.",
                    len(steps),
                    (plan.summary or "")[:80],
                )
                return "plan"

        # Plan exhausted: let verifier decide if task is done or we need to replan.
        return "verify"

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
    builder.add_node("verify", _node_verify)

    builder.add_edge(START, "navigate")
    builder.add_edge("navigate", "plan")
    builder.add_conditional_edges("plan", _route_after_plan, {"execute_step": "execute_step", "end": END})
    builder.add_conditional_edges(
        "execute_step",
        _route_after_execute,
        {"execute_step": "execute_step", "plan": "plan", "verify": "verify", "end": END},
    )
    builder.add_conditional_edges("verify", _route_after_verify, {"plan": "plan", "end": END})

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
            task.currentNode = node_name
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
            if "plan" in node_state:
                plan_obj = node_state["plan"]
                if plan_obj is not None:
                    task.planSummary = plan_obj.get("summary", "") if isinstance(plan_obj, dict) else getattr(plan_obj, "summary", "") or ""
                    decisions = plan_obj.get("decisions", []) if isinstance(plan_obj, dict) else getattr(plan_obj, "decisions", []) or []
                    task.planDecisions = [
                        {"actionType": (d.get("action") or {}).get("type", "click") if isinstance(d, dict) else getattr(getattr(d, "action", None), "type", "click"), "reasoning": d.get("reasoning", "") if isinstance(d, dict) else getattr(d, "reasoning", "")}
                        for d in decisions
                    ]
            if "decision_index" in node_state:
                task.currentDecisionIndex = node_state["decision_index"]
            if "verification_result" in node_state:
                task.verification_result = node_state["verification_result"]
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
