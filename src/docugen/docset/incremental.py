import hashlib

def hash_html(html: str) -> str:
    return hashlib.sha256(html.encode()).hexdigest()


class IncrementalCache:
    def __init__(self):
        self.cache = {}

    def changed(self, url, html):
        h = hash_html(html)
        if self.cache.get(url) != h:
            self.cache[url] = h
            return True
        return False
