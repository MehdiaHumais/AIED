"""Browser Tool - Playwright-based browser automation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrowserTool:
    """Browser automation using Playwright."""

    def __init__(self) -> None:
        self.browser = None
        self.context = None

    async def initialize(self, headless: bool = True) -> None:
        """Initialize Playwright browser."""
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(headless=headless)
            self.context = await self.browser.new_context()
            logger.info("Browser tool initialized")
        except ImportError:
            logger.warning("Playwright not installed. Browser tool unavailable.")

    async def close(self) -> None:
        """Close browser."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, "_playwright"):
            await self._playwright.stop()

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navigate to a URL."""
        if not self.context:
            raise RuntimeError("Browser not initialized")
        page = await self.context.new_page()
        await page.goto(url)
        return {"url": page.url, "title": await page.title()}

    async def screenshot(self, url: str, path: str | None = None) -> str | bytes:
        """Take a screenshot of a page."""
        if not self.context:
            raise RuntimeError("Browser not initialized")
        page = await self.context.new_page()
        await page.goto(url)
        screenshot = await page.screenshot(path=path, full_page=True)
        return screenshot

    async def get_page_content(self, url: str) -> str:
        """Get page HTML content."""
        if not self.context:
            raise RuntimeError("Browser not initialized")
        page = await self.context.new_page()
        await page.goto(url)
        return await page.content()


__all__ = ["BrowserTool"]
