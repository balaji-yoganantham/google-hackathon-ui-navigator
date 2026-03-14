"""Singleton browser pool for Playwright (one shared browser/page)."""
import asyncio
import logging

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

MAX_INIT_RETRIES = 3
RETRY_DELAY_SEC = 2


class BrowserPool:
    _instance: "BrowserPool | None" = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "BrowserPool":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_playwright"):
            return
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._initialized = False

    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized and self._browser and self._browser.is_connected():
                return

            last_error: Exception | None = None
            for attempt in range(1, MAX_INIT_RETRIES + 1):
                try:
                    logger.info("BrowserPool initializing (attempt %s/%s)", attempt, MAX_INIT_RETRIES)
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--no-zygote",
                            "--disable-software-rasterizer",
                            "--disable-extensions",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-background-networking",
                        ],
                    )
                    self._context = await self._browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 720},
                    )
                    self._page = await self._context.new_page()

                    await self._page.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
                    )
                    self._initialized = True
                    logger.info("BrowserPool initialized")
                    return
                except Exception as e:
                    last_error = e
                    logger.warning("BrowserPool attempt %s failed: %s", attempt, e)
                    await self.close()
                    if attempt < MAX_INIT_RETRIES:
                        await asyncio.sleep(RETRY_DELAY_SEC)
            logger.error("BrowserPool all initialization attempts failed")
            raise last_error or RuntimeError("Browser init failed")

    async def get_page(self) -> Page:
        if (
            not self._browser
            or not self._page
            or not self._browser.is_connected()
            or self._page.is_closed()
        ):
            logger.info("BrowserPool disconnected or page closed, reinitializing")
            await self.close()
            await self.initialize()
        if not self._page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        return self._page

    def _is_navigation_context_error(self, e: Exception) -> bool:
        msg = str(e).lower()
        return (
            "execution context was destroyed" in msg
            or "most likely because of a navigation" in msg
        )

    async def ensure_page_ready(self) -> None:
        try:
            page = await self.get_page()
            await page.evaluate("true")
        except Exception as e:
            if self._is_navigation_context_error(e) and self._page and not self._page.is_closed():
                logger.info("BrowserPool: context destroyed (navigation), waiting for new page to load")
                try:
                    await self._page.wait_for_load_state("load", timeout=15_000)
                    return
                except Exception as wait_e:
                    logger.warning("BrowserPool wait after navigation failed: %s", wait_e)
            logger.warning("BrowserPool page not responsive: %s", e)
            await self.close()
            await self.initialize()

    async def close(self) -> None:
        async with self._lock:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None
            self._initialized = False
            logger.info("BrowserPool closed")

    def is_initialized(self) -> bool:
        return self._initialized


browser_pool = BrowserPool()
