from abc import ABC, abstractmethod

class FetchResult:
    def __init__(self, url: str, html: str):
        self.url = url
        self.html = html


class Fetcher(ABC):
    def __init__(self):
        self.verbose_callback = None

    def set_verbose_callback(self, callback):
        self.verbose_callback = callback

    def v_log(self, message):
        if self.verbose_callback:
            self.verbose_callback(message)

    @abstractmethod
    async def fetch(self, url: str) -> FetchResult:
        pass
