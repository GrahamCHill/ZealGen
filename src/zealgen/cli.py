import argparse
import anyio
from .core import generate, DEFAULT_MAX_PAGES

def main():
    p = argparse.ArgumentParser()
    p.add_argument("urls", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--js", action="store_true")
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    def log(m):
        print(m)

    def verbose_log(m):
        if args.verbose:
            print(f"DEBUG: {m}")

    anyio.run(generate, args.urls, args.out, args.js, args.max_pages, None, None, "playwright", log, verbose_log)
