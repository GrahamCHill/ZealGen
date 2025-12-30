import httpx
from .base import Fetcher, FetchResult


class HttpxFetcher(Fetcher):
    async def fetch(self, url: str) -> FetchResult:
        self.v_log(f"Fetching with httpx: {url}")
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url, timeout=15)
            r.raise_for_status()
            return FetchResult(str(r.url), r.text)
