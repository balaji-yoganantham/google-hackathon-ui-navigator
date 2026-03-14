"""Async Playwright browser controller: navigate, screenshot, labels, executeAction, smartWait."""
import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import Page

from models.schemas import BrowserAction
from utils.browser_pool import browser_pool

logger = logging.getLogger(__name__)

DEFAULT_SCREENSHOT_QUALITY = 60
REMOVE_LABELS_SCRIPT = "document.querySelectorAll('.wayfinder-label').forEach(el => el.remove());"


def _normalize_wayfinder_selector(selector: str | None) -> str | None:
    """If the model returns only the label number (e.g. '10'), convert to [data-wayfinder-id='10']."""
    if not selector or not str(selector).strip():
        return selector
    s = str(selector).strip()
    if s.startswith("[data-wayfinder-id="):
        return s
    if s.isdigit():
        return f'[data-wayfinder-id="{s}"]'
    return s


def _load_label_script() -> str:
    path = Path(__file__).resolve().parent / "label_elements.js"
    return path.read_text(encoding="utf-8")


class BrowserController:
    def __init__(self) -> None:
        self._label_script = _load_label_script()

    async def navigate_to_url(self, url: str) -> None:
        await self._with_page_retry(self._navigate, "navigateToUrl", url=url)

    async def _navigate(self, page: Page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_load_state("load", timeout=5_000)

    async def add_labels(self) -> None:
        await self._with_page_retry(self._add_labels, "addLabels")

    async def _add_labels(self, page: Page, **kwargs: object) -> None:
        await page.evaluate(self._label_script)

    async def remove_labels(self) -> None:
        await self._with_page_retry(self._remove_labels, "removeLabels")

    async def _remove_labels(self, page: Page, **kwargs: object) -> None:
        await page.evaluate(REMOVE_LABELS_SCRIPT)

    async def screenshot(
        self,
        *,
        quality: int = DEFAULT_SCREENSHOT_QUALITY,
        full_page: bool = False,
        clip_to_viewport: bool = True,
    ) -> bytes:
        result = await self._with_page_retry(
            self._take_screenshot,
            "screenshot",
            quality=quality,
            full_page=full_page,
            clip_to_viewport=clip_to_viewport,
        )
        return result

    async def _take_screenshot(
        self,
        page: Page,
        *,
        quality: int = DEFAULT_SCREENSHOT_QUALITY,
        full_page: bool = False,
        clip_to_viewport: bool = True,
        **kwargs: object,
    ) -> bytes:
        viewport = page.viewport_size
        clip = None
        if clip_to_viewport and not full_page and viewport:
            clip = {"x": 0, "y": 0, "width": viewport["width"], "height": viewport["height"]}
        buf = await page.screenshot(
            type="jpeg",
            quality=quality,
            full_page=full_page,
            clip=clip,
        )
        return buf if isinstance(buf, bytes) else bytes(buf)

    async def smart_wait(self, max_ms: int = 500) -> None:
        page = await browser_pool.get_page()
        try:
            await asyncio.wait_for(
                page.wait_for_load_state("networkidle", timeout=max_ms),
                timeout=max_ms / 1000.0 + 1,
            )
        except (asyncio.TimeoutError, Exception):
            await asyncio.sleep(max_ms / 1000.0)

    async def stabilise_page(self) -> None:
        """Wait for network quiet and dismiss common overlays before planning screenshots."""
        await self._with_page_retry(self._stabilise_page_impl, "stabilise_page")

    async def _stabilise_page_impl(self, page: Page, **kwargs: object) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        dismiss_selectors = [
            "[data-test-modal-close-btn]",
            "button[aria-label='Dismiss']",
            ".msg-overlay-bubble-header__controls button",
            "[data-control-name='overlay.dismiss']",
        ]
        for sel in dismiss_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=500):
                    await btn.click(timeout=500)
                    await asyncio.sleep(0.3)
            except Exception:
                continue

    async def wait_for_load_after_navigation(self, timeout_ms: int = 12_000) -> None:
        """Wait for the page to finish loading after a navigation-causing action (press Enter, click link, goto)."""
        page = await browser_pool.get_page()
        try:
            await page.wait_for_load_state("load", timeout=timeout_ms)
        except Exception as e:
            logger.debug("wait_for_load_after_navigation: %s", e)

    async def element_exists(self, selector: str) -> bool:
        page = await browser_pool.get_page()
        el = await page.query_selector(selector)
        return el is not None

    async def execute_action(self, action: BrowserAction) -> str:
        try:
            return await self._with_page_retry(
                self._execute_action_impl,
                f"executeAction:{action.type}",
                action=action,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to execute action: {e}") from e

    async def _execute_action_impl(
        self,
        page: Page,
        *,
        action: BrowserAction,
        **kwargs: object,
    ) -> str:
        selector = _normalize_wayfinder_selector(action.selector) if action.selector else None
        t = action.type
        if t == "click":
            if not selector:
                raise ValueError("Selector required for click action")
            await page.wait_for_selector(selector, timeout=3_000)
            el = await page.query_selector(selector)
            if not el:
                raise ValueError(f"Element not found: {selector}")
            await el.scroll_into_view_if_needed()
            await el.click(delay=50, force=True)
            return f"Clicked on {selector}"

        if t == "type":
            if not selector or not action.text:
                raise ValueError("Selector and text required for type action")
            await page.wait_for_selector(selector, timeout=3_000)
            el = await page.query_selector(selector)
            if not el:
                raise ValueError(f"Element not found: {selector}")

            # Determine whether the element is directly fillable (input/textarea/select/contenteditable).
            # Buttons and other triggers must be clicked first to reveal an actual input.
            tag = await el.evaluate("e => e.tagName.toLowerCase()")
            is_contenteditable = await el.evaluate("e => !!e.isContentEditable")
            role = await el.evaluate("e => (e.getAttribute('role') || '').toLowerCase()")
            directly_fillable = (
                tag in ("input", "textarea", "select")
                or is_contenteditable
                or role in ("textbox", "searchbox", "combobox")
            )

            if directly_fillable:
                # Scroll the element into view first so Playwright can click it
                # even when it starts outside the visible viewport.
                await el.scroll_into_view_if_needed()
                await el.click()
                await page.fill(selector, action.text)
                return f'Typed "{action.text}" in {selector}'

            # Element is a trigger (e.g. a button that opens a search dialog).
            # Scroll into view then click to open the dialog.
            await el.scroll_into_view_if_needed()
            await el.click()
            await asyncio.sleep(0.6)  # Allow dialog/modal animation to complete

            # Check whether focus moved to an input or textarea automatically.
            try:
                focused_is_input = await page.evaluate(
                    "() => ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName || '')"
                )
                if focused_is_input:
                    await page.keyboard.type(action.text, delay=20)
                    return f'Typed "{action.text}" via focused dialog input after clicking {selector}'
            except Exception:
                pass

            # Scan common dialog/popover selectors for a visible text input.
            dialog_input_selectors = [
                "dialog input:not([type='hidden'])",
                "[role='dialog'] input:not([type='hidden'])",
                "[role='combobox']",
                "[role='searchbox']",
                "input[type='search']",
                "input[type='text']",
            ]
            for input_sel in dialog_input_selectors:
                try:
                    found = await page.wait_for_selector(input_sel, state="visible", timeout=1_500)
                    if found:
                        await found.fill(action.text)
                        return f'Typed "{action.text}" in dialog input ({input_sel}) after clicking {selector}'
                except Exception:
                    continue

            # Final fallback: type via keyboard (handles non-standard focusable inputs).
            await page.keyboard.type(action.text, delay=20)
            return f'Typed "{action.text}" via keyboard after clicking {selector}'

        if t == "scroll":
            amount = action.amount or 500
            await page.evaluate(f"window.scrollBy(0, {amount})")
            return f"Scrolled by {amount}px"

        if t == "navigate":
            if not action.url:
                raise ValueError("URL required for navigate action")
            await page.goto(action.url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_load_state("load", timeout=5_000)
            return f"Navigated to {action.url}"

        if t == "wait":
            delay = action.delay or 1000
            await asyncio.sleep(delay / 1000.0)
            return f"Waited for {delay}ms"

        if t == "screenshot":
            await self.screenshot()
            return "Screenshot taken"

        if t == "hover":
            if not selector:
                raise ValueError("Selector required for hover action")
            await page.wait_for_selector(selector, timeout=3_000)
            await page.hover(selector)
            return f"Hovered over {selector}"

        if t == "press":
            if not action.key:
                raise ValueError("Key required for press action")
            await page.keyboard.press(action.key)
            return f"Pressed key {action.key}"

        return "Unknown action"

    async def _with_page_retry(
        self,
        fn: Callable[..., Any],
        label: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        try:
            await browser_pool.ensure_page_ready()
            page = await browser_pool.get_page()
            return await fn(page, *args, **kwargs)
        except Exception as e:
            if self._is_page_closed_error(e):
                logger.info("BrowserController page closed during %s, reinitializing", label)
                await browser_pool.close()
                await browser_pool.initialize()
                page = await browser_pool.get_page()
                return await fn(page, *args, **kwargs)
            raise

    @staticmethod
    def _is_page_closed_error(err: Exception) -> bool:
        msg = str(getattr(err, "message", err) or "")
        return (
            "Target page, context or browser has been closed" in msg
            or "has been closed" in msg
            or "browser has been closed" in msg
        )
