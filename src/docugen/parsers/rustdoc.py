from bs4 import BeautifulSoup
from .base import Parser, ParsedPage

class RustdocParser(Parser):
    def matches(self, html):
        return "rustdoc" in html or "class=\"rustdoc\"" in html

    def parse(self, html):
        soup = BeautifulSoup(html, "lxml")
        title = soup.find("title").text if soup.find("title") else "Untitled"
        
        symbols = []
        # Rustdoc uses specific classes for items
        for item in soup.select(".item-name[id], .method[id], .type[id], .constant[id]"):
            name = item.text.strip()
            type_ = "Item"
            if "method" in item.get("class", []):
                type_ = "Method"
            elif "type" in item.get("class", []):
                type_ = "Type"
            elif "constant" in item.get("class", []):
                type_ = "Constant"
                
            symbols.append((name, type_, item["id"]))
            
        return ParsedPage(title, html, symbols)
