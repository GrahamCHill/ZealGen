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
        
        # 1. Same base domain (e.g. wiki.libsdl.org and examples.libsdl.org)
        # Any subdomain or the domain itself is allowed.
        if next_base_domain and next_base_domain == start_base_domain:
            return True

        # 2. Heuristic for related patterns on ANY domain (maybe too broad? Let's keep it to same base domain for now
        # but the original code was doing it for any domain if it reached there).
        # Actually, the original code ONLY did it if next_domain == start_domain.
        # Wait, let me re-read the original code.
    
    return False

async def scan(urls, js=False, max_pages=None, progress_callback=None, fetcher_type="playwright", log_callback=None, verbose_callback=None):
    if max_pages is None:
        max_pages = DEFAULT_MAX_PAGES
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)

    def v_log(message):
        if verbose_callback:
            verbose_callback(message)
        elif log_callback:
            log_callback(f"[VERBOSE] {message}")
        else:
            print(f"DEBUG: {message}")

    v_log(f"Starting scan for: {urls}")
    if js:
        v_log(f"JavaScript enabled, using {fetcher_type}")
        if fetcher_type == "qt" and QtFetcher:
            fetcher = QtFetcher()
        else:
            fetcher = PlaywrightFetcher()
    else:
        v_log("JavaScript disabled, using httpx")
        fetcher = HttpxFetcher()
    
    if hasattr(fetcher, 'set_verbose_callback'):
        fetcher.set_verbose_callback(v_log)
    
    visited = set()
    queue = []
    # Use a set to keep track of which URLs in the queue are internal
    for u in urls:
        queue.append((u, True)) # (url, is_internal)
    
    discovered = set()
    external_pages_count = 0

    while queue:
        url, is_internal = queue.pop(0)
        norm_url = normalize_url(url)
        if norm_url in visited:
            v_log(f"Skipping already visited: {url}")
            continue
        
        # If it's external, check if we've reached the limit
        if not is_internal:
            if external_pages_count >= max_pages:
                v_log(f"Max external pages ({max_pages}) reached, skipping: {url}")
                continue
        
        visited.add(norm_url)
        discovered.add(url)
        
        status_msg = f"Processing ({external_pages_count + 1 if not is_internal else 'internal'}/{max_pages if not is_internal else 'unlimited'}): {url}"
        v_log(status_msg)
        if progress_callback:
            # We still need to pass something to progress_callback. 
            # If we don't know the total internal pages, maybe just pass current counts.
            progress_callback(external_pages_count, max_pages)
        
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

        if not is_internal:
            external_pages_count += 1
        
        # Link discovery
        soup = BeautifulSoup(result.html, "lxml")
        current_url = result.url

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
            
            norm_clean_url = normalize_url(clean_url)
            
            if norm_clean_url not in visited:
                # Add to discovered even if not within doc, so user can choose it
                discovered.add(clean_url)

                is_next_internal = is_url_within_doc(clean_url, urls)
                
                # Check if it's already in queue
                already_in_queue = any(normalize_url(q_url) == norm_clean_url for q_url, _ in queue)
                
                if not already_in_queue:
                    if is_next_internal:
                        v_log(f"Found new internal link: {clean_url}")
                        queue.append((clean_url, True))
                    elif is_internal:
                        # Only follow external links if they are found on an INTERNAL page
                        if external_pages_count < max_pages:
                            v_log(f"Found external link: {clean_url}")
                            queue.append((clean_url, False))
                        else:
                            v_log(f"Max external pages reached, not adding link: {clean_url}")
                    else:
                        v_log(f"External link found on external page, not following: {clean_url}")

    return sorted(list(discovered))

async def generate(urls, output, js=False, max_pages=None, progress_callback=None, allowed_urls=None, fetcher_type="playwright", log_callback=None, verbose_callback=None):
    if max_pages is None:
        max_pages = DEFAULT_MAX_PAGES
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)

    def v_log(message):
        if verbose_callback:
            verbose_callback(message)
        elif log_callback:
            log_callback(f"[VERBOSE] {message}")
        else:
            print(f"DEBUG: {message}")

    v_log(f"Starting generation to {output}")
    if not urls:
        return

    main_url = urls[0]
    norm_main_url = normalize_url(main_url)

    if js:
        v_log(f"JavaScript enabled, using {fetcher_type}")
        if fetcher_type == "qt" and QtFetcher:
            fetcher = QtFetcher()
        else:
            fetcher = PlaywrightFetcher()
    else:
        v_log("JavaScript disabled, using httpx")
        fetcher = HttpxFetcher()
    
    if hasattr(fetcher, 'set_verbose_callback'):
        fetcher.set_verbose_callback(v_log)
    
    builder = DocsetBuilder(output, main_url=main_url, log_callback=log_callback)
    doc_dir = pathlib.Path(builder.documents_path)
    
    visited = set()
    queue = []
    for u in urls:
        queue.append((u, True))
    
    external_pages_count = 0

    if allowed_urls:
        allowed_urls = {normalize_url(u) for u in allowed_urls}
        # Ensure initial URLs are always allowed
        allowed_urls.update({normalize_url(u) for u in urls})

    while queue:
        url, is_internal = queue.pop(0)
        norm_url = normalize_url(url)
        if norm_url in visited:
            v_log(f"Skipping already visited: {url}")
            continue
        
        if allowed_urls and norm_url not in allowed_urls:
            v_log(f"Skipping URL not in allowed list: {url}")
            continue
        
        # If it's external, check if we've reached the limit
        # BUT: if it's explicitly allowed (e.g. via GUI selection), don't skip it.
        if not is_internal and not (allowed_urls and norm_url in allowed_urls):
            if external_pages_count >= max_pages:
                v_log(f"Max external pages ({max_pages}) reached, skipping: {url}")
                continue

        visited.add(norm_url)
        
        v_log(f"Fetching and processing ({external_pages_count + 1 if not is_internal else 'internal'}/{max_pages if not is_internal else 'unlimited'}): {url}")
        if progress_callback:
            progress_callback(external_pages_count, max_pages)
        
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

        if not is_internal:
            external_pages_count += 1

        if not builder.has_icon:
            favicon_url = get_favicon_url(result.html, url)
            await builder.set_icon(favicon_url)

        # Link discovery and rewriting
        soup = BeautifulSoup(result.html, "lxml")
        current_url = result.url

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
            
            norm_clean_url = normalize_url(clean_url)
            
            # Decision to follow link:
            # 1. If it's explicitly in allowed_urls
            # 2. OR if it matches the domain/path heuristic (stay within same documentation)
            # 3. OR if we are on an internal page and have budget for external ones (CLI discovery)
            is_allowed = bool(allowed_urls and norm_clean_url in allowed_urls)
            is_next_internal = is_url_within_doc(clean_url, urls)
            
            should_localize = is_allowed or is_next_internal or (is_internal and not allowed_urls and external_pages_count < max_pages)

            next_url_is_same_page = False
            
            # Check if next_url is the same page as current_url (ignoring fragment)
            if clean_url.split("#")[0] == current_url.split("#")[0]:
                next_url_is_same_page = True

            if should_localize:
                if next_url_is_same_page and anchor and element.name == "a":
                    element[attr] = f"#{anchor}"
                else:
                    local_name = get_filename_from_url(clean_url)
                    element[attr] = f"{local_name}#{anchor}" if anchor else local_name
                
                # Check if we should add it to the queue
                if norm_clean_url not in visited:
                    already_in_queue = any(normalize_url(q_url) == norm_clean_url for q_url, _ in queue)
                    if not already_in_queue:
                        if is_next_internal:
                            v_log(f"Added internal link to queue: {clean_url}")
                            queue.append((clean_url, True))
                        elif is_internal:
                             # Only follow external links if found on an internal page
                             if is_allowed or (not allowed_urls and external_pages_count < max_pages):
                                v_log(f"Added external link to queue: {clean_url}")
                                queue.append((clean_url, False))
            else:
                # If it's not within doc and not allowed, at least make it absolute if it was relative
                # so it doesn't break in the flat docset structure.
                v_log(f"External/disallowed link, keeping absolute: {next_url}")
                element[attr] = next_url
        
        updated_html = await rewrite_assets(str(soup), url, doc_dir)
        
        # Determine norm_url for comparison with main_url
        norm_url = normalize_url(url)
        # Also check against the final URL in case of redirects
        norm_final_url = normalize_url(result.url)
        
        # The first URL in the list is always considered the main page
        is_main = (url == urls[0] or norm_url == norm_main_url or norm_final_url == norm_main_url)
        
        # Ensure DOCTYPE exists
        if not updated_html.lstrip().lower().startswith("<!doctype"):
            updated_html = "<!DOCTYPE html>\n" + updated_html

        for parser in PARSERS:
            if parser.matches(updated_html):
                parsed = parser.parse(updated_html)
                builder.add_page(parsed, url, is_main=is_main)
                break

    if progress_callback:
        progress_callback(external_pages_count, max_pages)

    builder.finalize()
