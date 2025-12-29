import anyio
import sys
import os

# Add src to sys.path
sys.path.append(os.path.join(os.getcwd(), "../src"))

from zealgen.core import scan, generate
from zealgen.fetch.playwright_fetcher import PlaywrightFetcher

async def test_threejs():
    print("Testing Three.js...")
    urls = ["https://threejs.org/docs/"]
    # Test scan
    discovered = await scan(urls, js=True, max_pages=10)
    print(f"Three.js scan discovered {len(discovered)} pages.")
    
    # Check if we have some example pages
    has_examples = any("examples" in d for d in discovered)
    print(f"Three.js has example pages: {has_examples}")
    if has_examples:
        example_pages = [d for d in discovered if "examples" in d]
        print(f"Found {len(example_pages)} example pages, e.g.: {example_pages[:3]}")
    else:
        # Print some discovered pages to see what we got
        print(f"Discovered pages: {discovered[:10]}")

async def test_vulkan():
    print("\nTesting Vulkan...")
    urls = ["https://docs.vulkan.org/"]
    # Test scan
    discovered = await scan(urls, js=False, max_pages=5)
    print(f"Vulkan scan discovered {len(discovered)} pages.")
    for d in discovered:
        print(f" - {d}")
    
    # Check if the redirected URL was handled
    has_spec = any("spec/latest" in d for d in discovered)
    print(f"Vulkan has spec pages: {has_spec}")

async def main():
    await test_threejs()
    await test_vulkan()

if __name__ == "__main__":
    anyio.run(main)
