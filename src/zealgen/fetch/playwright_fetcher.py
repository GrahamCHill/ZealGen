from .base import Fetcher, FetchResult


class PlaywrightFetcher(Fetcher):
    async def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise Exception("Playwright is not installed. Please run 'pip install playwright'.")
            
        try:
            async with async_playwright() as pw:
                try:
                    browser = await pw.chromium.launch()
                except Exception as e:
                    if "playwright install" in str(e).lower():
                        raise Exception("Playwright browsers not installed. Please run 'playwright install chromium'.")
                    raise e
                    
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle")
                # Wait a bit more for any JS to finish rendering content
                await page.wait_for_timeout(5000)
                html = await page.content()
                await browser.close()
                return FetchResult(url, html)
        except Exception as e:
            raise Exception(f"Playwright error: {e}")
