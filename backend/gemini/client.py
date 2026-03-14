"""Gemini client via langchain-google-genai (API key) or langchain-google-vertexai (Vertex AI)."""
import base64
import json
import logging
import re
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

TASK COMPLETION RULES:
- "Search for X" or "search and tell me results": You MUST plan multiple steps: (1) type the query in the search box, (2) submit the search (press Enter or click the search button). Set taskComplete=true only on the final step when results are visible.
- "Click the first result": Plan steps until the result page has loaded. Set taskComplete=true on the step that loads the result.
- "Fill form and submit": Plan type + submit steps. Set taskComplete=true when submission is done (page changed or confirmation visible).
- "Navigate to URL": One navigate step is enough; set taskComplete=true.
- If the user asks to "search and tell me" or "find results", the plan must include submitting the search, not just typing.

ACTION TYPES:
- "click": Click element [data-wayfinder-id='X'] where X is the red label number
- "type": Type text into input field (selector and text required)
- "scroll": Scroll the page (helpful for finding labels)
- "navigate": Go to URL directly
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
✓ Set taskComplete=true only on the LAST decision when the goal is achieved (e.g. search results visible).
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
        response = await self._llm.ainvoke(messages)
        text = getattr(response, "content", None) or ""
        if isinstance(text, list):
            text = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in text
            )
        text = (text or "").strip()
        if not text:
            logger.warning("Model returned empty content for task: %s", task_description[:80])
            raise ValueError("Model returned an empty response. Try a shorter or simpler task.")
        parsed = self._parse_json_response(text)
        return GeminiResponse.model_validate(parsed)

    async def resolve_start_url(self, task_description: str) -> str:
        """Given a task description, ask Gemini for the single best starting URL (text-only)."""
        prompt = (
            f"Given this task: '{task_description}', reply with only the single best starting URL "
            "(e.g. https://www.google.com). No explanation, just the URL."
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
