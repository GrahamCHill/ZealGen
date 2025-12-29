import argparse
import anyio
from .core import generate, DEFAULT_MAX_PAGES

def main():
    p = argparse.ArgumentParser()
    p.add_argument("urls", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--js", action="store_true")
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    args = p.parse_args()

    anyio.run(generate, args.urls, args.out, args.js, args.max_pages)
