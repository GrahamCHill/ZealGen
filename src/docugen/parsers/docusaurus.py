from bs4 import BeautifulSoup
from .base import Parser, ParsedPage

class DocusaurusParser(Parser):
    def matches(self, html):
        return "docusaurus" in html or "__docusaurus" in html

    def parse(self, html):
        soup = BeautifulSoup(html, "lxml")
        title = soup.find("title").text if soup.find("title") else "Untitled"
        
        symbols = []
        # Docusaurus often uses h1, h2, h3 for sections with ids
        for heading in soup.select("h1[id], h2[id], h3[id]"):
            symbols.append((heading.text.strip(), "Section", heading["id"]))
            
        return ParsedPage(title, html, symbols)
