"""Gemini client via langchain-google-genai (API key) or langchain-google-vertexai (Vertex AI)."""
import asyncio
import base64
import json
import logging
import re
import warnings
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from models.schemas import GeminiResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Wayfinder AI, an intelligent web automation agent with exceptional visual understanding capabilities.

Your role:
1. Analyze website screenshots to understand the UI layout and available actions
2. Interpret user intent from natural language commands
3. Execute actions decisively and efficiently
4. Mark tasks complete when the goal is achieved

CURRENT PAGE STATE (read carefully before planning):
- The browser is ALREADY navigated to a page. The screenshot shows exactly where the browser is right now.
- NEVER plan a "navigate" action to the same site or a simpler version of the current URL (e.g. do NOT navigate to amazon.in if the screenshot already shows amazon.in content).
- If a [Current URL: ...] hint is provided in the task, treat that as the live browser location.
- Plan ONLY the steps needed FROM the current screenshot state to complete the remaining task.
- If results/content are already partially visible, continue from there — never restart by re-navigating.

TASK COMPLETION RULES:
- "Search for X": MUST plan multiple steps: (1) type the query in the search box, (2) submit (press Enter or click search button). Set taskComplete=true only when results are visible.
- "Click the first result": Plan steps until the result page has loaded.
- "Fill form and submit": Plan type + submit steps. Set taskComplete=true when submission is confirmed.
- "Navigate to URL": One navigate step is enough; set taskComplete=true.
- If the user asks to "search and tell me" or "find results", the plan must include submitting the search, not just typing.
- "Login / sign in task": MUST plan ALL steps: (1) if on homepage, click the Sign in link to reach the login form, (2) type the username/email into the username field, (3) type the password into the password field, (4) click the Sign in / Login button. Set taskComplete=true ONLY after the login button is clicked, not before. A single click to navigate to the login page is NEVER the complete task.

COMPLEX MULTI-STEP TASKS (filtering, sorting, form interactions):
- Tasks with keywords "filter", "sort", "4 star", "under ₹X / $X", "price range", "category", "rating": require AT LEAST 3 decisions.
- Do NOT collapse a filter/sort task into a single navigate step — you must click the actual filter UI elements.
- For "search AND filter" tasks: (1) confirm/enter search term, (2) click the correct filter option in the filter panel, (3) verify filtered results. Never skip step 2.
- A "navigate" to a pre-built search URL does NOT count as applying a filter — filters must be clicked in the UI.
- If you see a filter/sort panel on screen, use it by clicking the relevant labeled element.

MULTI-REQUIREMENT TASKS — PLAN ALL STEPS UPFRONT:
- If the task contains multiple distinct goals (e.g. "search + filter + find item + get price"), you MUST plan ALL of them in a SINGLE response, not just the first one.
- NEVER set taskComplete=true after only completing the first goal (e.g., after just searching). taskComplete=true is ONLY allowed when EVERY specific requirement in the original task is satisfied.
- Requirements checklist: before setting taskComplete=true, verify each requirement is done:
    • "search for X" → search submitted and results visible ✓
    • "filter by X" → filter checkbox/option clicked ✓
    • "find item with X badge/label" → item with that badge located and visible on screen ✓
    • "get the price" → price of the specific item identified and mentioned in reasoning ✓
    • "save/bookmark/click" → that specific action performed ✓
- For tasks that require scrolling to find a specific item or badge, include explicit scroll steps in the plan.
- A task like "search → filter → find item → get price" needs at minimum 5-6 decisions:
    (1) type search query, (2) submit search, (3) click filter option, (4) scroll results, (5) identify item with badge, (6) note price.
- Do NOT summarize multiple requirements into one decision — each UI action is one decision.

ACTION TYPES:
- "click": Click element [data-wayfinder-id='X'] where X is the red label number
- "type": Type text into input field (selector and text required)
- "scroll": Scroll the page (helpful for revealing more labels or filter panels)
- "navigate": Go to a completely different URL (use sparingly — only when the task explicitly requires it)
- "wait": Delay (optional)
- "hover": Hover over element
- "press": Press keyboard key (Enter, Space, Escape, etc)

JSON RESPONSE FORMAT:
{
  "decisions": [
    {"action": {"type": "type", "selector": "[data-wayfinder-id=\"10\"]", "text": "query"}, "reasoning": "...", "confidence": 0.9},
    {"action": {"type": "press", "key": "Enter"}, "reasoning": "Submit search", "confidence": 0.9}
  ],
  "summary": "brief overall strategy",
  "taskComplete": false,
  "nextSteps": ["optional"]
}
- "decisions" = the FULL plan: list ALL steps needed to complete the task in order.
- Do NOT return only one step when the task needs multiple (search = type + submit; filter = click filter option; form = fill + submit).
- For "Search for X and tell me results": include at least 2 decisions: (1) type X in search box, (2) press Enter or click search button.
- Example selector for red number 10: "selector": "[data-wayfinder-id=\"10\"]" (not just "10").

POP-UP / OVERLAY AWARENESS (check FIRST before planning anything else):
- Scan the screenshot for modals, pop-ups, cookie/GDPR banners, newsletter prompts, login walls, or any overlay that partially or fully blocks the main content.
- Common signals: a darkened backdrop behind a floating card, a banner fixed at the bottom/top of the page, a dialog with an ✕ / "Close" / "Accept" / "Dismiss" / "No thanks" button.
- If ANY such overlay is visible, your FIRST decision MUST be to dismiss it (click its close button by label number, or press Escape).
- CRITICAL: Dismissing a pop-up is NEVER the final step — it is ALWAYS step 1 of a longer plan. After the dismiss decision, you MUST include ALL remaining task steps (search, click, type, save, etc.) in the SAME plan.
- NEVER set taskComplete=true on a pop-up dismiss step. Set taskComplete=false on it and continue planning the actual task.
- If the close button is labeled (e.g. red number 3 is an ✕ button on the modal), decision 1 = {"type":"click","selector":"[data-wayfinder-id=\"3\"]"}, then decisions 2, 3, 4... = actual task steps.
- Do NOT plan actions on elements hidden behind an overlay — they are not reachable until after dismissal.

REQUIREMENT CHECKLIST RULES (when the task or prompt lists specific remaining requirements):
✓ The task is NOT complete until ALL requirements are satisfied. If ANY requirement (e.g. filter, find item, get price) is missing from your plan, set taskComplete=false.
✓ If the prompt includes "REMAINING REQUIREMENTS" or "at least N decisions", you MUST return at least N items in the "decisions" array. Returning fewer is invalid and will be rejected.
✓ If the prompt includes "REMAINING REQUIREMENTS" or a list of requirements, your plan MUST include at least one step for EACH listed requirement. Do not return a single scroll or single action when multiple requirements remain — that is invalid.
✓ Minimum steps: if there are N remaining requirements, your plan must contain at least N decisions. One step cannot satisfy multiple distinct requirements (e.g. filter + find deal + price = at least 3 steps).

CRITICAL RULES:
✓ SELECTOR: Use ONLY [data-wayfinder-id="N"] where N is the red number on the element. NEVER use aria-label, class, id, or any other selector.
✓ Always mention the label number in reasoning (e.g. "Type into search box labeled 10").
✓ Plan the FULL sequence: return 2-6 decisions when the task needs multiple actions.
✓ Set taskComplete=true only on the LAST decision when the goal is fully achieved.
✓ NO markdown code blocks - pure JSON only"""


class GeminiClient:
    """LangChain wrapper for screenshot + task → action plan (Gemini API or Vertex AI)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or settings.GOOGLE_API_KEY
        self._model = model or settings.GEMINI_MODEL

        if settings.USE_VERTEX_AI:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")
                from langchain_google_vertexai import ChatVertexAI
                self._llm = ChatVertexAI(
                    model=self._model,
                    project=settings.GOOGLE_CLOUD_PROJECT,
                    location=settings.GOOGLE_CLOUD_LOCATION,
                    temperature=0.2,
                    max_output_tokens=2048,
                )
            logger.info("GeminiClient initialized (Vertex AI) model=%s project=%s", self._model, settings.GOOGLE_CLOUD_PROJECT)
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            self._llm = ChatGoogleGenerativeAI(
                model=self._model,
                google_api_key=self._api_key,
                temperature=0.2,
                max_retries=0,
            )
            logger.info("GeminiClient initialized (API key) model=%s", self._model)

    async def plan_task(
        self, screenshot_bytes: bytes, task_description: str
    ) -> GeminiResponse:
        """Async: screenshot + task → GeminiResponse."""
        base64_str = base64.b64encode(screenshot_bytes).decode("utf-8")
        user_content: list[dict] = [
            {
                "type": "image",
                "base64": base64_str,
                "mime_type": "image/jpeg",
            },
            {
                "type": "text",
                "text": f"Task: {task_description}\n\nAnalyze the screenshot (red numbers are interactive elements). Return a JSON object with 'decisions', 'summary', 'taskComplete', and optionally 'nextSteps'. Use [data-wayfinder-id='N'] for selectors. One action per decision for this step.",
            },
        ]
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):  # up to 3 attempts
            try:
                response = await self._llm.ainvoke(messages)
                text = getattr(response, "content", None) or ""
                if isinstance(text, list):
                    text = "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in text
                    )
                text = (text or "").strip()
                if not text:
                    raise ValueError("Model returned an empty response.")
                parsed = self._parse_json_response(text)
                return GeminiResponse.model_validate(parsed)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # Retry on empty, JSON/parse errors (e.g. "Expecting ',' delimiter", "invalid JSON")
                is_retryable = (
                    "empty" in err_str or "json" in err_str or "invalid response" in err_str
                    or "expecting" in err_str or "delimiter" in err_str or "parse" in err_str
                )
                if is_retryable:
                    if attempt < 3:
                        delay = 1.5 * attempt
                        logger.warning(
                            "Plan attempt %s/3 failed (%s), retrying in %.1fs...",
                            attempt,
                            str(e)[:60],
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(
                            "Model returned empty or invalid content for task: %s (after 3 attempts)",
                            task_description[:80],
                        )
                        raise ValueError(
                            "Model returned an empty or invalid response after retries. Try a shorter or simpler task."
                        ) from last_error
                else:
                    raise
        raise ValueError(
            "Model returned an empty or invalid response after retries. Try a shorter or simpler task."
        ) from last_error

    async def resolve_start_url(self, task_description: str) -> str:
        """Given a task description, ask Gemini for the single best starting URL (text-only)."""
        prompt = (
            f"Given this task: '{task_description}', reply with ONLY the base homepage URL of the "
            "website where the task should start (e.g. https://www.amazon.in, "
            "https://www.linkedin.com, https://www.github.com). "
            "IMPORTANT: Do NOT construct search URLs or URLs with query parameters or filters. "
            "Return only the bare homepage domain so the agent can navigate step-by-step through "
            "the UI. No explanation, just the URL."
        )
        messages = [HumanMessage(content=prompt)]
        response = await self._llm.ainvoke(messages)
        text = getattr(response, "content", None) or ""
        if isinstance(text, list):
            text = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in text
            )
        url = (text or "").strip()
        if not url or not url.lower().startswith("http"):
            logger.info("[resolve_start_url] Invalid or empty URL from model, using https://www.google.com")
            return "https://www.google.com"
        return url

    @staticmethod
    def _parse_json_response(raw: str) -> dict:
        """Extract JSON object from model output (strip markdown if present)."""
        raw = (raw or "").strip()
        if not raw:
            raise ValueError("Model returned empty response; cannot parse JSON.")
        # Remove optional markdown code fence
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
            raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract a single JSON object from the response (model may have added prose)
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start : end + 1])
            raise ValueError(
                "Model response was not valid JSON. Try rephrasing the task or avoiding sensitive content (e.g. passwords)."
            ) from None
