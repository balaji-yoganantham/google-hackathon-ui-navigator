"""Gemini client via langchain-google-genai (API key) or langchain-google-vertexai (Vertex AI)."""
import base64
import json
import logging
import re
import warnings
from typing import Optional
from urllib.parse import urlparse, urlunparse

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

TASK COMPLETION RULES:
- "Search for X" or "search and tell me results": You MUST plan multiple steps: (1) type the query in the search box, (2) submit the search (press Enter or click the search button). Set taskComplete=true only on the final step when results are visible.
- "Click the first result": Plan steps until the result page has loaded. Set taskComplete=true on the step that loads the result.
- "Fill form and submit": Plan type + submit steps. Set taskComplete=true when submission is done (page changed or confirmation visible).
- "Navigate to URL": Use a single "navigate" step ONLY when the user explicitly asks to open a specific URL (e.g. "open this exact URL"). Otherwise do NOT use navigate to jump to search results or filtered pages.
- If the user asks to "search and tell me" or "find results", the plan must include submitting the search, not just typing.

MULTI-PHASE TASK RULES (important for tasks like "search and then play/click/open"):
- You only see the CURRENT page in the screenshot. Plan only the actions visible on this page.
- If the task requires actions on a FUTURE page (e.g. click search result, click play on video), do NOT try to plan those now. Set taskComplete=false and the system will re-plan after the current actions run.
- Set taskComplete=true ONLY when the ENTIRE user goal is fully achieved — e.g. the video is playing, the result page is open, the form was submitted.
- EXAMPLES:
  * Task: "play Madan Gowri recent video" on YouTube home → Plan: [type "madan gowri", press Enter]. taskComplete=false. After re-plan on results page → Plan: [click first video]. taskComplete=true.
  * Task: "search for jobs on LinkedIn" on LinkedIn home → Plan: [click Jobs, type "Senior AI Engineer", press Enter]. taskComplete=false. After re-plan on results page → taskComplete=true.
  * Task: "open Google and search cats" on Google home → Plan: [type "cats", press Enter]. After re-plan when results visible → taskComplete=true.

STUCK / REPEATED STEPS RULE:
- If "Steps already executed" shows you already tried the same action (e.g. type + click search, or type + click button) and the Current page URL has NOT changed to a results page, that approach did NOT work.
- In that case, use a DIFFERENT method: if you clicked a button, try "press Enter" instead. If you pressed Enter, try clicking the submit button with a different label number.
- Never plan the exact same sequence of actions if the prior attempt failed to change the page.

NAVIGATION RULES (step-by-step like a user):
- You start on the site's base/home page. Do NOT plan a "navigate" action to a URL that contains search query params or deep links (e.g. /jobs/search?keywords=..., /results?search_query=...).
- For job search, product search, or any "search for X" task: plan actions from the CURRENT page (click search box, type, press Enter or click search). Never use "navigate" to a pre-built search URL unless the user literally says "open this exact URL".
- Prefer: type + press Enter (or click search button). Use "navigate" only when the user explicitly requests opening a specific URL.

ACTION TYPES:
- "click": Click element [data-wayfinder-id='X'] where X is the red label number
- "type": Type text into input field (selector and text required)
- "scroll": Scroll the page (helpful for finding labels)
- "navigate": Go to URL directly — use ONLY when user explicitly asks to open a specific URL; do not use for search/filter deep links
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
- "decisions" = the FULL plan: list ALL steps needed to complete the task in order (e.g. for search: step 1 type, step 2 press Enter or click search). Do NOT return only one step when the task needs multiple.
- For "Search for X and tell me results": include at least 2 decisions: (1) type X in search box, (2) press Enter or click search button. Set taskComplete=true only on the last decision.
- Example selector for red number 10: "selector": "[data-wayfinder-id=\"10\"]" (not just "10").

CRITICAL RULES:
✓ SELECTOR: Use ONLY [data-wayfinder-id="N"] where N is the red number on the element. NEVER use aria-label, class, id, or any other selector.
✓ Always mention the label number in reasoning (e.g. "Type into search box labeled 10").
✓ Plan the FULL sequence: return 2-6 decisions when the task needs multiple actions (search = type + submit; form = fill + submit).
✓ Set taskComplete=true ONLY when the ENTIRE user goal is done (video playing, result open, etc.). If more steps will be needed from a new page, set taskComplete=false — the system re-plans automatically.
✓ Do NOT use a "navigate" decision to a search-URL or filtered-URL; plan from current UI (type in search box, press Enter, click buttons).
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
                    temperature=0,
                    max_output_tokens=3000,
                )
            logger.info(
                "GeminiClient initialized (Vertex AI) model=%s project=%s max_output_tokens=3000",
                self._model, settings.GOOGLE_CLOUD_PROJECT,
            )
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
        self,
        screenshot_bytes: bytes,
        task_description: str,
        steps_done: list[str] | None = None,
        current_url: str | None = None,
    ) -> GeminiResponse:
        """Async: screenshot + task → GeminiResponse.

        Retries up to 3 times on both empty responses AND non-JSON responses.
        Uses a simplified prompt on retry attempts to reduce token pressure.
        """
        import asyncio as _asyncio

        logger.info(
            "[plan_task] START task=%.80s url=%s steps_done=%d",
            task_description, current_url or "unknown", len(steps_done or []),
        )

        base64_str = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Build context block — shared by both full and minimal prompts
        context_parts = []
        if current_url:
            context_parts.append(f"Current page URL: {current_url}")
        if steps_done:
            steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps_done))
            context_parts.append(
                f"ALREADY COMPLETED — DO NOT repeat any of these steps, pick up from where they left off:\n{steps_text}"
            )
        context_block = ("\n\n" + "\n".join(context_parts)) if context_parts else ""

        full_prompt = (
            f"Task: {task_description}{context_block}\n\n"
            "Analyze the screenshot (red numbers are interactive elements). "
            "Determine the NEXT action(s) needed to make progress — do NOT redo any already-completed step. "
            "Return a JSON object with 'decisions', 'summary', 'taskComplete', and optionally 'nextSteps'. "
            "Use [data-wayfinder-id='N'] for selectors. One action per decision for this step."
        )
        # Minimal fallback prompt — still includes URL + history so the model doesn't lose context
        minimal_prompt = (
            f"Task: {task_description}{context_block}\n\n"
            "Look at the screenshot and decide the NEXT single action to make progress. "
            "Do NOT repeat any step already listed above. "
            "Return ONLY a raw JSON object (no markdown) in this exact shape:\n"
            "{\"decisions\":[{\"action\":{\"type\":\"click\",\"selector\":\"[data-wayfinder-id=\\\"N\\\"]\"},"
            "\"reasoning\":\"reason\",\"confidence\":0.9}],\"summary\":\"...\",\"taskComplete\":false}"
        )

        def _build_messages(prompt: str) -> list:
            return [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=[
                    {"type": "image", "base64": base64_str, "mime_type": "image/jpeg"},
                    {"type": "text", "text": prompt},
                ]),
            ]

        max_retries = 3
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            use_prompt = full_prompt if attempt == 1 else minimal_prompt
            messages = _build_messages(use_prompt)

            logger.debug("[plan_task] attempt %d/%d — invoking model", attempt, max_retries)
            response = await self._llm.ainvoke(messages)
            raw = getattr(response, "content", None) or ""
            if isinstance(raw, list):
                raw = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw
                )
            text = (raw or "").strip()

            if not text:
                logger.warning(
                    "[plan_task] attempt %d/%d — EMPTY response from model | task=%.80s",
                    attempt, max_retries, task_description,
                )
                last_error = ValueError("Model returned an empty response.")
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.info("[plan_task] waiting %ds before retry...", wait)
                    await _asyncio.sleep(wait)
                continue

            logger.debug("[plan_task] attempt %d/%d — raw response: %.400s", attempt, max_retries, text)

            try:
                parsed = self._parse_json_response(text)
                result = GeminiResponse.model_validate(parsed)
                if attempt > 1:
                    logger.info(
                        "[plan_task] SUCCESS on attempt %d/%d | decisions=%d summary=%.60s",
                        attempt, max_retries, len(result.decisions), result.summary or "",
                    )
                else:
                    logger.info(
                        "[plan_task] SUCCESS | decisions=%d summary=%.60s",
                        len(result.decisions), result.summary or "",
                    )
                return result
            except Exception as parse_err:
                logger.warning(
                    "[plan_task] attempt %d/%d — BAD JSON: %s | raw (first 400 chars): %.400s",
                    attempt, max_retries, parse_err, text,
                )
                last_error = parse_err
                if attempt < max_retries:
                    wait = 2 ** attempt
                    logger.info("[plan_task] waiting %ds before retry with simplified prompt...", wait)
                    await _asyncio.sleep(wait)

        logger.error(
            "[plan_task] FAILED after %d attempts | last_error=%s | task=%.80s",
            max_retries, last_error, task_description,
        )
        raise last_error or ValueError("Model failed to return valid JSON after all retries.")

    async def resolve_start_url(self, task_description: str) -> str:
        """Given a task description, return the best starting URL (preserving service paths, no query params)."""
        logger.info("[resolve_start_url] Resolving URL for task: %.80s", task_description)
        prompt = (
            f"Given this task: '{task_description}', reply with ONLY the best starting URL for this task. "
            "Rules: (1) No query parameters or search filters. "
            "(2) If the task uses a specific Google sub-service, use its direct URL "
            "(e.g. https://www.google.com/flights for flight searches, "
            "https://www.google.com/maps for maps, https://www.google.com/travel for hotels). "
            "(3) For other sites use their home page "
            "(e.g. https://www.linkedin.com, https://www.youtube.com, https://www.amazon.com). "
            "(4) Include the path if it is a well-known service landing page, but no search query paths. "
            "Reply with only the URL, no explanation."
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
            logger.warning(
                "[resolve_start_url] Model returned invalid/empty URL ('%s'), falling back to https://www.google.com",
                url,
            )
            return "https://www.google.com"
        final_url = self._to_base_url(url)
        logger.info("[resolve_start_url] Resolved: '%s' → %s", task_description[:60], final_url)
        return final_url

    @staticmethod
    def _to_base_url(url: str) -> str:
        """Strip only query params and fragment; preserve scheme, host, and service path."""
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return url
            # Keep path (e.g. /flights, /maps) but strip query and fragment
            clean_path = parsed.path.rstrip("/")
            clean = urlunparse((parsed.scheme, parsed.netloc, clean_path, "", "", ""))
            if clean != url:
                logger.info("[resolve_start_url] Normalized URL (stripped params): %s -> %s", url, clean)
            return clean
        except Exception as e:
            logger.warning("[resolve_start_url] Failed to normalize URL %s: %s", url, e)
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
