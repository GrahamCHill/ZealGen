from playwright.async_api import async_playwright
from .base import Fetcher, FetchResult


class PlaywrightFetcher(Fetcher):
    async def fetch(self, url: str) -> FetchResult:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            # Wait a bit more for any JS to finish rendering content
            await page.wait_for_timeout(2000)
            html = await page.content()
            await browser.close()
            return FetchResult(url, html)
