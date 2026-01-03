from bs4 import BeautifulSoup
from .base import Parser, ParsedPage


class GenericParser(Parser):
    def matches(self, html: str) -> bool:
        return True

    def parse(self, html: str) -> ParsedPage:
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        title = title_tag.text if title_tag else "Untitled"

        symbols = []
        # Basic symbol extraction from h1, h2 if they have ids
        for tag in soup.find_all(["h1", "h2", "h3"]):
            if tag.get("id"):
                symbols.append((tag.text.strip(), "Section", tag["id"]))

        return ParsedPage(title, html, symbols)
