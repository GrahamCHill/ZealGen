import anyio
import pathlib
import os
from dotenv import load_dotenv
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

from .utils.url import get_filename_from_url, normalize_url, clean_domain, get_base_domain

# Load environment variables from .env file
load_dotenv()

DEFAULT_MAX_PAGES = int(os.getenv("TOTAL_PAGES", 250))

PARSERS = [
    sphinx.SphinxParser(),
    docusaurus.DocusaurusParser(),
    rustdoc.RustdocParser(),
    generic.GenericParser(),
]

def is_url_within_doc(url, start_urls, related_patterns=None):
    if related_patterns is None:
        related_patterns = ["/examples", "/samples", "/demo", "/docs", "/api", "/manual", "/wiki"]
    
    next_parsed = urlparse(url)
    next_domain = clean_domain(next_parsed.netloc)
    next_base_domain = get_base_domain(next_domain)
    
    # Check against all start URLs
    for start_url in start_urls:
        start_parsed = urlparse(start_url)
        start_domain = clean_domain(start_parsed.netloc)
        start_base_domain = get_base_domain(start_domain)
        
        # 1. Exact domain match
        if next_domain == start_domain:
            base_path = start_parsed.path.rsplit('/', 1)[0]
            if not base_path.endswith('/'):
                base_path += '/'
            
            if next_parsed.path.startswith(base_path):
                return True

        # 2. Same base domain (e.g. wiki.libsdl.org and examples.libsdl.org)
        if next_base_domain and next_base_domain == start_base_domain:
            # For same base domain, we are more relaxed but still check for documentation-like patterns
            # or if it's under a similar path structure.
            is_related = any(p in next_parsed.path.lower() for p in related_patterns)
            # Also check if netloc contains related patterns (e.g. examples.libsdl.org)
            is_related = is_related or any(p.strip("/") in next_parsed.netloc.lower() for p in related_patterns)
            
            if is_related:
                return True
            
            # If the start URL path is just / or /SDL3/, and the next URL is also under /SDL3/
            # even on a different subdomain of the same base domain, it's likely related.
            start_path = start_parsed.path
            if start_path and start_path != "/" and next_parsed.path.startswith(start_path):
                return True

    # 3. Heuristic for related patterns on ANY domain (maybe too broad? Let's keep it to same base domain for now
    # but the original code was doing it for any domain if it reached there).
    # Actually, the original code ONLY did it if next_domain == start_domain.
    # Wait, let me re-read the original code.
    
    return False

async def scan(urls, js=False, max_pages=None, progress_callback=None, fetcher_type="playwright", log_callback=None, verbose=False, cancel_event=None):
    if max_pages is None:
        max_pages = DEFAULT_MAX_PAGES
    
    def log(message, verbose_only=False):
        if verbose_only and not verbose:
            return
        if log_callback:
            try:
                log_callback(message, verbose_only=verbose_only)
            except TypeError:
                log_callback(message)
        else:
            print(message)

    log(f"Starting scan of {urls} (max_pages={max_pages}, js={js}, fetcher={fetcher_type})", verbose_only=True)

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
        if cancel_event and cancel_event.is_set():
            log("Scan cancelled by user.")
            break

        url = queue.pop(0)
        norm_url = normalize_url(url)
        if norm_url in visited:
            log(f"Skipping already visited URL: {url} (normalized: {norm_url})", verbose_only=True)
            continue
        visited.add(norm_url)
        discovered.add(url)
        
        log(f"Fetching ({pages_count + 1}/{max_pages}): {url}", verbose_only=True)
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
                        log(f"Final attempt failed for {url}: {e}")
                        raise e
                    log(f"Retry {attempt + 1}/{max_retries} for {url} due to: {e}")
                    await anyio.sleep(2 * (attempt + 1)) # Simple backoff
        except Exception as e:
            log(f"Failed to fetch {url} after {max_retries} attempts: {e}")
            continue

        pages_count += 1
        
        # Link discovery and rewriting
        soup = BeautifulSoup(result.html, "lxml")
        current_url = result.url
        base_parsed = urlparse(current_url)

        # Discovery of links in <a> tags and <iframe> src
        discovered_links = []
        for a in soup.find_all("a", href=True):
            discovered_links.append(a["href"])
        for iframe in soup.find_all("iframe", src=True):
            discovered_links.append(iframe["src"])

        for raw_value in discovered_links:
            # If it's a simple fragment link, skip for discovery
            if raw_value.startswith("#"):
                continue

            next_url = urljoin(current_url, raw_value)
            
            # Use normalized URL for discovery decision
            norm_next_url = normalize_url(next_url)
            clean_url = next_url.split("#")[0]
            
            # If normalize_url preserved the fragment, we use the fragment-inclusive URL as clean_url
            if "#" in norm_next_url and "#" not in clean_url:
                clean_url = next_url # Keep the hash if it was deemed important for routing
            
            norm_url = normalize_url(clean_url)
            
            if norm_url not in visited and norm_url not in queue:
                # Add to discovered even if not within doc, so user can choose it
                discovered.add(clean_url)

                if is_url_within_doc(clean_url, urls):
                    if len(visited) < max_pages:
                        log(f"Discovered new link within doc: {clean_url}", verbose_only=True)
                        queue.append(clean_url)
                    else:
                        log(f"Max pages reached, not queueing: {clean_url}", verbose_only=True)
                else:
                    log(f"Discovered link outside doc (skipping crawl): {clean_url}", verbose_only=True)

    return sorted(list(discovered))

async def generate(urls, output, js=False, max_pages=None, progress_callback=None, allowed_urls=None, fetcher_type="playwright", log_callback=None, verbose=False, force=False, cancel_event=None):
    if max_pages is None:
        max_pages = DEFAULT_MAX_PAGES

    def log(message, verbose_only=False):
        if verbose_only and not verbose:
            return
        if log_callback:
            try:
                log_callback(message, verbose_only=verbose_only)
            except TypeError:
                log_callback(message)
        else:
            print(message)

    log(f"Starting generation to {output} (max_pages={max_pages}, js={js}, fetcher={fetcher_type}, force={force})", verbose_only=True)

    if not urls:
        return

    main_url = urls[0]
    norm_main_url = normalize_url(main_url)

    if js:
        if fetcher_type == "qt" and QtFetcher:
            fetcher = QtFetcher()
        else:
            fetcher = PlaywrightFetcher()
    else:
        fetcher = HttpxFetcher()
    builder = DocsetBuilder(output, main_url=main_url, log_callback=log_callback, verbose=verbose, force=force)
    doc_dir = pathlib.Path(builder.documents_path)
    
    visited = set()
    queue = list(urls)
    pages_count = 0

    if allowed_urls:
        allowed_urls = {normalize_url(u) for u in allowed_urls}
        # Ensure initial URLs are always allowed
        allowed_urls.update({normalize_url(u) for u in urls})

    while queue and pages_count < max_pages:
        if cancel_event and cancel_event.is_set():
            log("Generation cancelled by user.")
            break

        url = queue.pop(0)
        norm_url = normalize_url(url)
        if norm_url in visited:
            log(f"Skipping already visited URL: {url} (normalized: {norm_url})", verbose_only=True)
            continue
        
        if allowed_urls and norm_url not in allowed_urls:
            log(f"Skipping URL not in allowed list: {url}", verbose_only=True)
            continue

        visited.add(norm_url)
        log(f"Processing ({pages_count + 1}/{max_pages}): {url}", verbose_only=True)
        
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
                        log(f"Final attempt failed for {url}: {e}")
                        raise e
                    log(f"Retry {attempt + 1}/{max_retries} for {url} due to: {e}")
                    await anyio.sleep(2 * (attempt + 1)) # Simple backoff
        except Exception as e:
            log(f"Failed to fetch {url} after {max_retries} attempts: {e}")
            continue

        if not builder.has_icon:
            favicon_url = get_favicon_url(result.html, url)
            await builder.set_icon(favicon_url)

        # Link discovery and rewriting
        soup = BeautifulSoup(result.html, "lxml")
        current_url = result.url
        base_parsed = urlparse(current_url)

        # Discovery of links in <a> tags and <iframe> src
        links_to_process = []
        for a in soup.find_all("a", href=True):
            links_to_process.append((a, "href", a["href"]))
        for iframe in soup.find_all("iframe", src=True):
            links_to_process.append((iframe, "src", iframe["src"]))

        for element, attr, raw_value in links_to_process:
            # If it's a simple fragment link, keep it as is
            if raw_value.startswith("#"):
                continue

            next_url = urljoin(current_url, raw_value)
            
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
            next_domain = clean_domain(next_parsed.netloc)
            
            # Decision to follow link:
            # 1. If it's explicitly in allowed_urls
            # 2. OR if it matches the domain/path heuristic (stay within same documentation)
            is_allowed = bool(allowed_urls and normalize_url(clean_url) in allowed_urls)
            is_within_doc = is_url_within_doc(clean_url, urls)
            
            next_url_is_same_page = False
            
            # Check if next_url is the same page as current_url (ignoring fragment)
            if clean_url.split("#")[0] == current_url.split("#")[0]:
                next_url_is_same_page = True

            if is_allowed or is_within_doc:
                if next_url_is_same_page and anchor and element.name == "a":
                    element[attr] = f"#{anchor}"
                else:
                    local_name = get_filename_from_url(clean_url)
                    element[attr] = f"{local_name}#{anchor}" if anchor else local_name
                
                # Use normalized URL for checking visited/queue to be consistent
                norm_clean_url = normalize_url(clean_url)
                # But we still need the actual URL to fetch it
                if norm_clean_url not in visited and norm_clean_url not in queue:
                     # Only follow links that are allowed or within doc
                     if is_allowed or is_within_doc:
                        log(f"Queuing new link: {clean_url}", verbose_only=True)
                        queue.append(clean_url)
                     else:
                        log(f"Skipping link (not allowed/within doc): {clean_url}", verbose_only=True)
                elif norm_clean_url in visited:
                    log(f"Link already visited: {clean_url}", verbose_only=True)
                elif norm_clean_url in queue:
                    log(f"Link already in queue: {clean_url}", verbose_only=True)
            else:
                # If it's not within doc and not allowed, at least make it absolute if it was relative
                # so it doesn't break in the flat docset structure.
                element[attr] = next_url
        
        updated_html = await rewrite_assets(str(soup), url, doc_dir, force=force, verbose=verbose, log_callback=log_callback)
        
        # Determine norm_url for comparison with main_url
        norm_url = normalize_url(url)
        # Also check against the final URL in case of redirects
        norm_final_url = normalize_url(result.url)
        
        # The first URL in the list is always considered the main page
        is_main = (url == urls[0] or norm_url == norm_main_url or norm_final_url == norm_main_url)
        
        pages_count += 1
        
        # Ensure DOCTYPE exists
        if not updated_html.lstrip().lower().startswith("<!doctype"):
            updated_html = "<!DOCTYPE html>\n" + updated_html

        for parser in PARSERS:
            if parser.matches(updated_html):
                parsed = parser.parse(updated_html)
                builder.add_page(parsed, url, is_main=is_main)
                break

    if progress_callback:
        progress_callback(pages_count, max_pages)

    builder.finalize()
