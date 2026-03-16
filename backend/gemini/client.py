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
from models.schemas import ContentReport, GeminiResponse

logger = logging.getLogger(__name__)

# Backoff for rate limit (429 / resource exhausted): 10s, 30s, 60s
_RATE_LIMIT_BACKOFF = (10, 30, 60)


def _is_rate_limit_error(e: Exception) -> bool:
    """True if the exception indicates API rate limit (429) or resource exhausted."""
    msg = (str(e) or "").lower()
    return any(
        x in msg
        for x in ("429", "resource exhausted", "quota", "rate limit", "resource_exhausted")
    )


def _backoff_seconds(attempt: int, max_retries: int, is_rate_limit: bool) -> int:
    """Return wait time in seconds before retry."""
    if is_rate_limit:
        idx = min(attempt - 1, len(_RATE_LIMIT_BACKOFF) - 1)
        return _RATE_LIMIT_BACKOFF[idx]
    return 2**attempt


SYSTEM_PROMPT = """You are Visual Agent, an intelligent web automation agent with exceptional visual understanding capabilities.

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
- "click": Click element [data-visual-agent-id='X'] where X is the red label number
- "type": Type text into input field (selector and text required)
- "scroll": Scroll the page (helpful for finding labels)
- "navigate": Go to URL directly — use ONLY when user explicitly asks to open a specific URL; do not use for search/filter deep links
- "wait": Delay (optional)
- "hover": Hover over element
- "press": Press keyboard key (Enter, Space, Escape, etc)
- "extract": Extract and analyze content on the current page (PDF, YouTube transcript, or page text). Use when the user asks to summarize, extract, or report on the visible content. No selector needed.

EXTRACT FOR REPORT/RESEARCH TASKS:
- If the task contains "report", "analyze", "summarize", "research", or "tell me about", you MUST include an "extract" action as the FINAL decision when you have reached the target content page (e.g. after opening a Wikipedia article, a search result, or the page the user asked about). Do NOT set taskComplete=true without an extract step when the user asked for a report or analysis.

JSON RESPONSE FORMAT:
{
  "decisions": [
    {"action": {"type": "type", "selector": "[data-visual-agent-id=\"10\"]", "text": "query"}, "reasoning": "...", "confidence": 0.9},
    {"action": {"type": "press", "key": "Enter"}, "reasoning": "Submit search", "confidence": 0.9}
  ],
  "summary": "brief overall strategy",
  "taskComplete": false,
  "nextSteps": ["optional"]
}
- "decisions" = the FULL plan: list ALL steps needed to complete the task in order (e.g. for search: step 1 type, step 2 press Enter or click search). Do NOT return only one step when the task needs multiple.
- For "Search for X and tell me results": include at least 2 decisions: (1) type X in search box, (2) press Enter or click search button. Set taskComplete=true only on the last decision.
- Example selector for red number 10: "selector": "[data-visual-agent-id=\"10\"]" (not just "10").

CRITICAL RULES:
✓ SELECTOR: Use ONLY [data-visual-agent-id="N"] where N is the red number on the element. NEVER use aria-label, class, id, or any other selector.
✓ Always mention the label number in reasoning (e.g. "Type into search box labeled 10").
✓ Plan the FULL sequence: return 2-6 decisions when the task needs multiple actions (search = type + submit; form = fill + submit).
✓ Set taskComplete=true ONLY when the ENTIRE user goal is done (video playing, result open, etc.). If more steps will be needed from a new page, set taskComplete=false — the system re-plans automatically.
✓ Do NOT use a "navigate" decision to a search-URL or filtered-URL; plan from current UI (type in search box, press Enter, click buttons).
✓ NO markdown code blocks - pure JSON only.
✓ For \"extract\" action use: {\"action\": {\"type\": \"extract\"}, \"reasoning\": \"...\", \"confidence\": 0.9}. No selector or text."""


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
                    max_output_tokens=8192,
                    max_retries=0,
                )
            logger.info(
                "GeminiClient initialized (Vertex AI) model=%s project=%s max_output_tokens=8192",
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
            "Use [data-visual-agent-id='N'] for selectors. One action per decision for this step."
        )
        # Minimal fallback prompt — still includes URL + history so the model doesn't lose context
        minimal_prompt = (
            f"Task: {task_description}{context_block}\n\n"
            "Look at the screenshot and decide the NEXT single action to make progress. "
            "Do NOT repeat any step already listed above. "
            "Return ONLY a raw JSON object (no markdown) in this exact shape:\n"
            "{\"decisions\":[{\"action\":{\"type\":\"click\",\"selector\":\"[data-visual-agent-id=\\\"N\\\"]\"},"
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
            try:
                response = await self._llm.ainvoke(messages)
            except Exception as e:
                last_error = e
                is_429 = _is_rate_limit_error(e)
                wait = _backoff_seconds(attempt, max_retries, is_429)
                logger.warning(
                    "[plan_task] attempt %d/%d — invoke failed: %s",
                    attempt, max_retries, e,
                )
                if is_429:
                    logger.info("[plan_task] Rate limit detected, backing off %ds before retry...", wait)
                if attempt < max_retries:
                    await _asyncio.sleep(wait)
                continue
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
                    wait = _backoff_seconds(attempt, max_retries, False)
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
                    wait = _backoff_seconds(attempt, max_retries, False)
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

    async def parse_audio_command(self, audio_b64: str, mime_type: str = "audio/webm") -> dict:
        """Send raw audio to Vertex AI Gemini; return {url, goal}. Uses same LLM as plan_task (Vertex or API key)."""
        if not audio_b64 or len(audio_b64) < 500:
            raise ValueError("AUDIO_TOO_SHORT")

        prompt = (
            "Listen to this voice command for a web automation agent. Extract the target URL and the goal. "
            "Return ONLY JSON with no markdown or code fences: {\"url\": \"https://...\", \"goal\": \"...\"}. "
            "If the user mentions a website name, construct the full URL (e.g. courtlistener -> https://www.courtlistener.com). "
            "Default URL to https://www.google.com if no domain is specified. "
            "Return ONLY the root base URL of the domain (no deep links or search paths). "
            "Put all search terms and instructions into the goal field. "
            "If the audio is only silence or unintelligible, return {\"url\": \"\", \"goal\": \"\"}. "
            "No markdown, no explanation, only JSON."
        )
        # LangChain multimodal: same structure as image; Gemini accepts inline_data with any mime_type
        messages = [
            HumanMessage(content=[
                {"type": "image", "base64": audio_b64, "mime_type": mime_type},
                {"type": "text", "text": prompt},
            ]),
        ]
        response = await self._llm.ainvoke(messages)
        raw = getattr(response, "content", None) or ""
        if isinstance(raw, list):
            raw = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw
            )
        text = (raw or "").strip()
        if not text:
            return {"url": "https://www.google.com", "goal": ""}
        try:
            parsed = self._parse_json_response(text)
        except Exception:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(text[start : end + 1])
            else:
                return {"url": "https://www.google.com", "goal": ""}
        url = (parsed.get("url") or "").strip()
        goal = (parsed.get("goal") or "").strip()
        if url and not url.lower().startswith("http"):
            url = self._resolve_spoken_site(url)
        if not url or not url.lower().startswith("http"):
            url = "https://www.google.com"
        return {"url": url, "goal": goal}

    @staticmethod
    def _resolve_spoken_site(spoken: str) -> str:
        """Map spoken site name to full URL (port of Citadelle SITE_MAP)."""
        site_map = {
            "youtube": "https://www.youtube.com",
            "wikipedia": "https://www.wikipedia.org",
            "reddit": "https://www.reddit.com",
            "twitter": "https://www.twitter.com",
            "github": "https://www.github.com",
            "courtlistener": "https://www.courtlistener.com",
            "court listener": "https://www.courtlistener.com",
            "oyez": "https://www.oyez.org",
            "google": "https://www.google.com",
            "linkedin": "https://www.linkedin.com",
            "stackoverflow": "https://stackoverflow.com",
            "stack overflow": "https://stackoverflow.com",
        }
        lower = spoken.lower().replace(" ", "").replace(".", "")
        for name, u in site_map.items():
            if name.replace(" ", "") in lower or lower in name.replace(" ", ""):
                return u
        cleaned = re.sub(r"[^a-zA-Z0-9.-]", "", spoken).lower()
        if cleaned and len(cleaned) < 50 and re.match(r"^[a-z0-9]", cleaned):
            return f"https://www.{cleaned if '.' in cleaned else cleaned + '.com'}"
        return "https://www.google.com"

    # Content-type-specific analysis prompts (Citadelle-style, ~800 words)
    _PROMPT_PDF = (
        "You are a Senior Legal Partner at a top-tier law firm. The user's goal is: \"{goal}\". "
        "Read this official court PDF text and write an EXTENSIVE, highly detailed legal analysis of AT LEAST 800 words "
        "organized into these sections:\n"
        "1. CASE BACKGROUND & PARTIES: Who are the parties, what is the dispute about, and what is the factual context?\n"
        "2. PROCEDURAL HISTORY: How did this case arrive at this court? What happened in lower courts?\n"
        "3. KEY LEGAL ISSUES: What are the central legal questions the court must resolve?\n"
        "4. COURT'S ANALYSIS & REASONING: How did the court analyze each issue? What legal tests or standards were applied?\n"
        "5. IMPORTANT PRECEDENTS CITED: Which prior cases did the court rely on, and how were they applied?\n"
        "6. CONTRADICTIONS & DISSENTING OPINIONS: Identify any contradictory arguments, conflicting statements, or dissenting opinions.\n"
        "7. HOLDING & VERDICT: What did the court ultimately decide?\n"
        "8. PRACTICAL IMPLICATIONS: What does this ruling mean for future cases or parties in similar situations?\n\n"
        "Write each section as a detailed paragraph. Be thorough — this is for a premium legal intelligence report. "
        "Return ONLY a valid JSON array with NO markdown: "
        '[{{"title": "Case Name", "court": "Court", "date": "Date", "docket": "Docket", "content": "Your extensive analysis here with all 8 sections"}}]. '
        "For list requests, return multiple objects."
    )
    _PROMPT_YOUTUBE = (
        "You are an expert content analyst and researcher. The user's goal is: \"{goal}\". "
        "Read this YouTube video transcript and write an EXTENSIVE, detailed analysis of AT LEAST 800 words. "
        "Structure your analysis into these sections:\n"
        "1. VIDEO OVERVIEW: What is this video about? Who is the speaker/creator and what is the context?\n"
        "2. MAIN ARGUMENTS & KEY POINTS: What are the primary arguments, claims, or topics discussed? Detail each major point thoroughly.\n"
        "3. SUPPORTING EVIDENCE & EXAMPLES: What evidence, data, stories, or examples does the speaker use to support their points?\n"
        "4. NOTABLE QUOTES & MOMENTS: Highlight any particularly impactful statements or pivotal moments in the video.\n"
        "5. CRITICAL ANALYSIS: What are the strengths and weaknesses of the arguments presented? Are there any biases or gaps?\n"
        "6. CONCLUSIONS & TAKEAWAYS: What are the final conclusions, and what should the viewer take away from this content?\n\n"
        "Write each section as a detailed paragraph. Be thorough — this is for a premium intelligence report. "
        "For the court field use the format \"Channel: <channel name>\" when you know the channel; otherwise \"Channel: Unknown\". "
        "Return ONLY a valid JSON array with no markdown: "
        '[{{"title": "...", "court": "Channel: ...", "date": "... or null", "docket": "", "content": "Your extensive 6-section analysis here"}}].'
    )
    _PROMPT_PAGE = (
        "You are a Research Analyst preparing a premium intelligence report. The user's goal is: \"{goal}\". "
        "Read this webpage text and write an EXTENSIVE, detailed analysis of AT LEAST 800 words. "
        "Structure your analysis into these sections:\n"
        "1. OVERVIEW: What is this page about? Who or what is the main subject? Provide context.\n"
        "2. KEY FACTS: The most important facts, dates, figures, and definitions.\n"
        "3. SIGNIFICANT DETAILS: Notable events, achievements, contributions, or developments.\n"
        "4. SUPPORTING CONTEXT: Background, sources, related topics, or how this fits into the bigger picture.\n"
        "5. CRITICAL ANALYSIS: Strengths, gaps, controversies, or different perspectives where relevant.\n"
        "6. SUMMARY: Concise conclusions and main takeaways.\n\n"
        "Write each section as a thorough paragraph. Ignore UI menus, navigation links, and ads. "
        "The content field must be YOUR written analysis/summary only — do NOT copy or paste raw webpage text. "
        "Return ONLY a valid JSON array with no markdown: "
        '[{{"title": "Page or topic title", "court": "Source or site name", "date": "Date if relevant or null", "docket": "", "content": "Your extensive 6-section analysis here"}}]. '
        "For list requests, return multiple objects."
    )
    _PROMPT_PAGE_SIMPLE = (
        "The user's goal is: \"{goal}\". "
        "Read the webpage text below and give a direct, brief answer in 1 to 3 sentences (e.g. price, product name, availability, or what was found). "
        "Ignore menus, navigation, and ads. Do NOT write a long analysis. "
        "Return ONLY a single JSON object with no markdown and no code fences: "
        '{{"title": "Short title for the result", "content": "Your 1-3 sentence answer here."}}'
    )

    _PROMPT_EXTRACT_SIMPLE = (
        "The user's goal is: \"{goal}\". "
        "Analyze the content below and return a JSON array of report objects. "
        "Each object must have \"title\" and \"content\". Content should be your analysis (at least a few paragraphs). "
        "Return ONLY a valid JSON array, no markdown. Example: [{{\"title\": \"...\", \"content\": \"...\"}}]."
    )

    _PROMPT_QA = (
        "You are a QA analyst. The user ran a QA scan on a webpage. "
        "Given the page text below (and page URL if relevant), list every issue you can infer. "
        "Check for: missing or empty image alt text, poor color contrast, broken or suspicious links (e.g. empty href, javascript:), "
        "form elements without labels, buttons/links with unclear purpose, layout or accessibility problems. "
        "For each issue provide: a short title, severity (critical / major / minor), a brief description, and a recommendation. "
        "Return ONLY a valid JSON array of objects, no markdown. Each object must have \"title\" and \"content\". "
        "Put description, severity, and recommendation in the \"content\" field (e.g. \"Severity: major. Description: ... Recommendation: ...\"). "
        "Example: [{{\"title\": \"Missing alt text on hero image\", \"content\": \"Severity: major. Description: The main image has no alt attribute. Recommendation: Add descriptive alt text.\"}}]. "
        "If no issues are found, return one object: {{\"title\": \"No issues found\", \"content\": \"No accessibility, link, or layout issues were detected from the provided content.\"}}."
    )

    _PROMPT_QA_SIMPLE = (
        "The user ran a QA scan on a webpage. Return a JSON array of objects. "
        "Each object must have \"title\" and \"content\" (issue title and description, or severity and recommendation). "
        "If no issues found, return one object: {{\"title\": \"No issues found\", \"content\": \"No issues detected.\"}}. "
        "Return ONLY a valid JSON array, no markdown."
    )

    async def extract_and_analyze(
        self, content: str, content_type: str, goal: str, page_url: str = ""
    ) -> list[ContentReport]:
        """Send extracted text/transcript to Vertex AI; return structured report list (content-type-specific prompts)."""
        import asyncio as _asyncio

        if not content or not content.strip():
            return [ContentReport(title="No content", url=page_url, content_type=content_type, content="No text extracted.")]
        ct = (content_type or "page").lower()
        if ct == "pdf":
            full_prompt_template = self._PROMPT_PDF
        elif ct == "youtube":
            full_prompt_template = self._PROMPT_YOUTUBE
        elif ct == "qa":
            full_prompt_template = self._PROMPT_QA
        else:
            goal_lower = (goal or "").lower()
            qa_keywords = ("qa scan", "qa scan on", "quality assurance", "run a qa")
            is_qa_scan = any(kw in goal_lower for kw in qa_keywords)
            if is_qa_scan:
                full_prompt_template = self._PROMPT_QA
                ct = "qa"
            else:
                simple_keywords = ("price", "cost", "how much", "find the", "search and tell", "what is the", "tell me the", "get the")
                is_simple_lookup = len(goal_lower) < 80 and any(kw in goal_lower for kw in simple_keywords)
                full_prompt_template = self._PROMPT_PAGE_SIMPLE if is_simple_lookup else self._PROMPT_PAGE
        # QA: smaller slice on first attempt so model has room to return full JSON
        if ct == "qa":
            logger.info("[extract_and_analyze] Using QA path (content_type=qa)")
        content_slice = content[:50000] if ct == "qa" else content[:120000]
        _fallback_msg = "Analysis could not be generated. Please try again or rephrase your query."
        _qa_no_issues = ContentReport(
            title="No issues found",
            url=page_url,
            content_type="qa",
            content="No accessibility, link, or layout issues were detected from the provided content.",
        )
        _qa_summary_title = "QA Scan Summary"
        _qa_summary_content = (
            "This QA scan completed. The automated analysis did not return structured findings. "
            "Review the Steps tab for the actions performed during the scan. You may re-run the scan or try a different page."
        )
        max_retries = 3
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            use_simple = attempt > 1
            if ct == "qa" and use_simple:
                prompt_template = self._PROMPT_QA_SIMPLE
            else:
                prompt_template = self._PROMPT_EXTRACT_SIMPLE if use_simple else full_prompt_template
            prompt = prompt_template.format(goal=goal) + "\n\n---\n" + (content_slice[:60000] if use_simple else content_slice)
            messages = [HumanMessage(content=prompt)]
            try:
                response = await self._llm.ainvoke(messages)
            except Exception as e:
                last_error = e
                is_429 = _is_rate_limit_error(e)
                wait = _backoff_seconds(attempt, max_retries, is_429)
                logger.warning("[extract_and_analyze] attempt %d/%d — invoke failed: %s", attempt, max_retries, e)
                if is_429:
                    logger.info("[extract_and_analyze] Rate limit detected, backing off %ds before retry...", wait)
                if attempt < max_retries:
                    await _asyncio.sleep(wait)
                continue
            raw = getattr(response, "content", None) or ""
            if isinstance(raw, list):
                raw = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw
                )
            text = (raw or "").strip()
            if not text:
                logger.warning(
                    "[extract_and_analyze] attempt %d/%d — empty response (content_type=%s)",
                    attempt, max_retries, ct,
                )
                last_error = ValueError("Model returned empty response.")
                if attempt < max_retries:
                    # Treat empty response as soft rate-limit — use long backoff (10s/30s/60s)
                    wait = _backoff_seconds(attempt, max_retries, True)
                    logger.info("[extract_and_analyze] Empty response likely from quota exhaustion, backing off %ds...", wait)
                    await _asyncio.sleep(wait)
                continue
            stripped = text.strip()
            if stripped.startswith("```"):
                stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
                stripped = re.sub(r"\s*```\s*$", "", stripped).strip()
            parsed: list = []
            for s in [stripped, text.strip()]:
                try:
                    if s.startswith("["):
                        start, end = s.find("["), s.rfind("]")
                        if start != -1 and end > start:
                            parsed = json.loads(s[start : end + 1])
                            if isinstance(parsed, list) and parsed:
                                break
                    arr_match = re.search(r"\[[\s\S]*\]", s)
                    if arr_match:
                        parsed = json.loads(arr_match.group(0))
                        if isinstance(parsed, list) and parsed:
                            break
                except (json.JSONDecodeError, ValueError):
                    continue
            if not parsed or not isinstance(parsed, list):
                try:
                    single = self._parse_json_response(stripped)
                    if single and isinstance(single, dict) and (single.get("title") or single.get("content")):
                        parsed = [single]
                except Exception:
                    pass
            # QA: try extracting single JSON object from first { to last }
            if (not parsed or not isinstance(parsed, list)) and ct == "qa":
                try:
                    start = stripped.find("{")
                    end = stripped.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        single = json.loads(stripped[start : end + 1])
                        if isinstance(single, dict) and (single.get("title") or single.get("content")):
                            parsed = [single]
                except (json.JSONDecodeError, ValueError):
                    pass
            if not isinstance(parsed, list):
                parsed = []
            reports = []
            for item in parsed:
                if isinstance(item, dict):
                    report_content = item.get("content") or item.get("summary") or item.get("analysis") or ""
                    reports.append(ContentReport(
                        title=item.get("title") or "Report",
                        url=item.get("url") or page_url,
                        date=item.get("date"),
                        content_type="qa" if ct == "qa" else (item.get("content_type") or content_type),
                        content=report_content,
                        court=item.get("court"),
                        docket=item.get("docket"),
                    ))
            # QA: empty parsed list or model said "no issues" in prose -> return No issues found
            if ct == "qa" and isinstance(parsed, list) and len(parsed) == 0:
                return [_qa_no_issues]
            if ct == "qa" and not reports and text and ("no issues" in text.lower() or "no problems" in text.lower()):
                return [_qa_no_issues]
            if reports:
                if attempt > 1:
                    logger.info("[extract_and_analyze] SUCCESS on attempt %d/%d", attempt, max_retries)
                return reports
            last_error = ValueError("No valid report objects in model response")
            if attempt < max_retries:
                wait = _backoff_seconds(attempt, max_retries, False)
                logger.info("[extract_and_analyze] retrying in %ds...", wait)
                await _asyncio.sleep(wait)
        logger.warning("[extract_and_analyze] FAILED after %d attempts", max_retries)
        if ct == "qa":
            return [ContentReport(
                title=_qa_summary_title,
                url=page_url,
                content_type="qa",
                content=_qa_summary_content,
            )]
        return [ContentReport(title="Analysis", url=page_url, content_type=content_type, content=_fallback_msg)]

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
