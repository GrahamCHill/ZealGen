import anyio
import pathlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from .fetch.httpx_fetcher import HttpxFetcher
from .fetch.playwright_fetcher import PlaywrightFetcher
try:
    from .fetch.qt_fetcher import QtFetcher
except ImportError:
    QtFetcher = None
from .parsers import sphinx, docusaurus, rustdoc, generic
from .docset.builder import DocsetBuilder
from .assets.rewrite import rewrite_assets, get_favicon_url

from .utils.url import get_filename_from_url, normalize_url

PARSERS = [
    sphinx.SphinxParser(),
    docusaurus.DocusaurusParser(),
    rustdoc.RustdocParser(),
    generic.GenericParser(),
]

async def scan(urls, js=False, max_pages=10, progress_callback=None, fetcher_type="playwright"):
    if js:
        if fetcher_type == "qt" and QtFetcher:
            fetcher = QtFetcher()
        else:
            fetcher = PlaywrightFetcher()
    else:
        fetcher = HttpxFetcher()
    
    visited = set()
    queue = list(urls)
    discovered = set()
    pages_count = 0

    while queue and pages_count < max_pages:
        url = queue.pop(0)
        norm_url = normalize_url(url)
        if norm_url in visited:
            continue
        visited.add(norm_url)
        discovered.add(url)
        
        if progress_callback:
            progress_callback(pages_count, max_pages)
        
        try:
            # Add retries for robustness
            max_retries = 3
            result = None
            for attempt in range(max_retries):
                try:
                    result = await fetcher.fetch(url)
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"Final attempt failed for {url}: {e}")
                        raise e
                    print(f"Retry {attempt + 1}/{max_retries} for {url} due to: {e}")
                    await anyio.sleep(2 * (attempt + 1)) # Simple backoff
        except Exception as e:
            print(f"Failed to fetch {url} after {max_retries} attempts: {e}")
            continue

        pages_count += 1
        
        # Link discovery and rewriting
        soup = BeautifulSoup(result.html, "lxml")
        current_url = result.url
        base_parsed = urlparse(current_url)
        for a in soup.find_all("a", href=True):
            next_url = urljoin(current_url, a["href"])
            
            # Use normalized URL for discovery decision
            norm_next_url = normalize_url(next_url)
            clean_url = next_url.split("#")[0]
            
            # If normalize_url preserved the fragment, we use the fragment-inclusive URL as clean_url
            if "#" in norm_next_url and "#" not in clean_url:
                clean_url = next_url # Keep the hash if it was deemed important for routing
            
            norm_url = normalize_url(clean_url)
            
            if norm_url not in visited and norm_url not in queue:
                # More robust within-doc check for scanning too
                is_within_doc = False
                for start_url in urls:
                    start_parsed = urlparse(start_url)
                    if urlparse(clean_url).netloc == start_parsed.netloc:
                        base_path = start_parsed.path.rsplit('/', 1)[0]
                        if not base_path.endswith('/'): base_path += '/'
                        if urlparse(clean_url).path.startswith(base_path):
                            is_within_doc = True
                            break
                
                if is_within_doc:
                    if len(visited) < max_pages:
                        queue.append(clean_url)
                
                discovered.add(clean_url)

    return sorted(list(discovered))

async def generate(urls, output, js=False, max_pages=100, progress_callback=None, allowed_urls=None, fetcher_type="playwright"):
    if js:
        if fetcher_type == "qt" and QtFetcher:
            fetcher = QtFetcher()
        else:
            fetcher = PlaywrightFetcher()
    else:
        fetcher = HttpxFetcher()
    builder = DocsetBuilder(output)
    doc_dir = pathlib.Path(builder.documents_path)
    
    visited = set()
    queue = list(urls)
    pages_count = 0

    if allowed_urls:
        allowed_urls = {normalize_url(u) for u in allowed_urls}
        # Ensure initial URLs are always allowed
        allowed_urls.update({normalize_url(u) for u in urls})

    while queue and pages_count < max_pages:
        url = queue.pop(0)
        norm_url = normalize_url(url)
        if norm_url in visited:
            continue
        
        if allowed_urls and norm_url not in allowed_urls:
            continue

        visited.add(norm_url)
        
        if progress_callback:
            progress_callback(pages_count, max_pages)
        
        try:
            # Add retries for robustness
            max_retries = 3
            result = None
            for attempt in range(max_retries):
                try:
                    result = await fetcher.fetch(url)
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"Final attempt failed for {url}: {e}")
                        raise e
                    print(f"Retry {attempt + 1}/{max_retries} for {url} due to: {e}")
                    await anyio.sleep(2 * (attempt + 1)) # Simple backoff
        except Exception as e:
            print(f"Failed to fetch {url} after {max_retries} attempts: {e}")
            continue

        if not builder.has_icon:
            favicon_url = get_favicon_url(result.html, url)
            await builder.set_icon(favicon_url)

        # Link discovery and rewriting
        soup = BeautifulSoup(result.html, "lxml")
        current_url = result.url
        base_parsed = urlparse(current_url)
        for a in soup.find_all("a", href=True):
            raw_href = a["href"]
            next_url = urljoin(current_url, raw_href)
            
            # Use normalized URL for discovery decision
            norm_next_url = normalize_url(next_url)
            clean_url = next_url.split("#")[0]
            
            # If normalize_url preserved the fragment, we use the fragment-inclusive URL as clean_url
            if "#" in norm_next_url and "#" not in clean_url:
                clean_url = next_url # Keep the hash if it was deemed important for routing
                anchor = None
            else:
                anchor = next_url.split("#")[1] if "#" in next_url else None
            
            next_parsed = urlparse(clean_url)
            
            # Decision to follow link:
            # 1. If it's explicitly in allowed_urls
            # 2. OR if it matches the domain/path heuristic (stay within same documentation)
            is_allowed = bool(allowed_urls and normalize_url(clean_url) in allowed_urls)
            
            # More robust within-doc check
            # We want to stay on the same domain and at or below the base path of the starting URLs
            is_within_doc = False
            for start_url in urls:
                start_parsed = urlparse(start_url)
                if next_parsed.netloc == start_parsed.netloc:
                    # Check if next_url is under the same base path
                    base_path = start_parsed.path.rsplit('/', 1)[0]
                    if not base_path.endswith('/'):
                        base_path += '/'
                    if next_parsed.path.startswith(base_path):
                        is_within_doc = True
                        break
            
            if is_allowed or is_within_doc:
                local_name = get_filename_from_url(clean_url)
                a["href"] = f"{local_name}#{anchor}" if anchor else local_name
                
                # Use normalized URL for checking visited/queue to be consistent
                norm_clean_url = normalize_url(clean_url)
                # But we still need the actual URL to fetch it
                if norm_clean_url not in visited and norm_clean_url not in queue:
                     if not allowed_urls or norm_clean_url in allowed_urls:
                        queue.append(clean_url)
            else:
                # If it's not within doc and not allowed, at least make it absolute if it was relative
                # so it doesn't break in the flat docset structure.
                a["href"] = next_url
        
        updated_html = await rewrite_assets(str(soup), url, doc_dir)
        pages_count += 1
        
        # Ensure DOCTYPE exists
        if not updated_html.lstrip().lower().startswith("<!doctype"):
            updated_html = "<!DOCTYPE html>\n" + updated_html

        for parser in PARSERS:
            if parser.matches(updated_html):
                parsed = parser.parse(updated_html)
                builder.add_page(parsed, url)
                break

    if progress_callback:
        progress_callback(pages_count, max_pages)

    builder.finalize()
