from abc import ABC, abstractmethod

class ParsedPage:
    def __init__(self, title, content, symbols):
        self.title = title
        self.content = content
        self.symbols = symbols  # [(name, type, anchor)]


class Parser(ABC):
    @abstractmethod
    def matches(self, html: str) -> bool:
        pass

    @abstractmethod
    def parse(self, html: str) -> ParsedPage:
        pass
