from bs4 import BeautifulSoup
from .base import Parser, ParsedPage


class SphinxParser(Parser):
    def matches(self, html):
        return "sphinx_rtd_theme" in html or "docutils" in html

    def parse(self, html):
        soup = BeautifulSoup(html, "lxml")
        title = soup.find("title").text

        symbols = []
        for dt in soup.select("dt[id]"):
            symbols.append((dt.text.strip(), "Function", dt["id"]))

        return ParsedPage(title, html, symbols)
