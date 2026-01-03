from abc import ABC, abstractmethod

class FetchResult:
    def __init__(self, url: str, html: str):
        self.url = url
        self.html = html


class Fetcher(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> FetchResult:
        pass
