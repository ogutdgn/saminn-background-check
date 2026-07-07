"""Shared Playwright browser manager for Tier-4 (browser-only) adapters.

One Playwright Chromium process lives for the lifetime of the app (launched at startup,
closed at shutdown by the FastAPI lifespan hook). Each search gets a fresh BrowserContext
(isolated cookies / session) so state never leaks between searches. Adapters receive a
BrowserManager via ctx.browser and call new_page() to get a ready Page.

Stealth: Incapsula (the bot-protection Collin County uses) checks navigator.webdriver
and a handful of JS fingerprints at page load. We patch those via init_script on every
new context so the fingerprint check sees a real-looking browser. The playwright-stealth
package applies the standard set of patches (webdriver flag, plugins, languages, etc.).

Usage by an adapter:
    async with ctx.browser.new_page() as page:
        await page.goto(URL)
        ...  # interact with the page
        html = await page.content()
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright_stealth import Stealth

_stealth = Stealth()

# A desktop Chrome UA consistent with what the orchestrator uses for HTTP sources.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Chromium launch args that make the browser look less like a bot.
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]


class BrowserManager:
    """Wraps one long-lived Playwright Browser process.

    Instantiated once at app startup; adapters call new_page() to get a
    stealth-patched Page inside an isolated BrowserContext that is automatically
    closed when the `async with` block exits.
    """

    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._pw = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Launch the browser. Called once at app startup."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=_LAUNCH_ARGS,
        )

    async def stop(self) -> None:
        """Close the browser and the playwright driver. Called at app shutdown."""
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = None
        self._pw = None

    @asynccontextmanager
    async def new_page(self) -> AsyncIterator[Page]:
        """Yield a stealth-patched Page inside a fresh, isolated BrowserContext.

        The context (and its page) is closed automatically when the block exits,
        so cookies / local storage / cache never bleed between searches.
        """
        if self._browser is None:
            raise RuntimeError("BrowserManager.start() was never called")

        ctx: BrowserContext = await self._browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        page: Page = await ctx.new_page()
        await _stealth.apply_stealth_async(page)
        try:
            yield page
        finally:
            await ctx.close()
