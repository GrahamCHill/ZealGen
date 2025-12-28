from urllib.parse import urlparse

def clean_domain(netloc: str) -> str:
    """Remove www. from the domain."""
    domain = netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain

def normalize_url(url: str) -> str:
    """Normalize URL for comparison by stripping scheme, www, and trailing slashes.
    Preserves fragment if it looks like a route (e.g. for Three.js)."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    
    path = parsed.path.rstrip("/")
    if not path:
        path = ""
    
    # Special handling for hash-based routing (e.g. Three.js)
    fragment = parsed.fragment
    use_fragment = False
    if fragment and ("/" in fragment or "api" in fragment.lower() or "manual" in fragment.lower()):
        use_fragment = True
    elif fragment and len(fragment) > 3 and not any(c in fragment for c in " ."):
        # If the fragment is reasonably long and doesn't look like a simple anchor
        # (contains no spaces or dots), it might be a route.
        # This is a heuristic and might need refinement.
        use_fragment = True

    query = parsed.query
    res = f"{netloc}{path}"
    if query:
        res += f"?{query}"
    if use_fragment and fragment:
        res += f"#{fragment}"
        
    return res.lower()

def get_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    # Use cleaned domain for the filename prefix
    domain = clean_domain(parsed.netloc)
    
    path = parsed.path
    if not path or path.endswith("/"):
        path += "index.html"
    
    # Remove leading slash
    if path.startswith("/"):
        path = path[1:]
    
    # Special handling for hash-based routing (e.g. Three.js)
    fragment = parsed.fragment
    use_fragment = False
    if fragment and ("/" in fragment or "api" in fragment.lower() or "manual" in fragment.lower()):
        use_fragment = True
    elif fragment and len(fragment) > 3 and not any(c in fragment for c in " ."):
        use_fragment = True
    
    if use_fragment and fragment:
        # Sanitize fragment for filename
        safe_fragment = fragment.replace("/", "_").replace("#", "_").replace("?", "_")
        if path.endswith(".html"):
            path = path[:-5] + "_" + safe_fragment + ".html"
        else:
            path = path + "_" + safe_fragment
    
    query = parsed.query
    if query:
        # Replace characters that are not safe for filenames in query
        safe_query = query.replace("=", "_").replace("&", "_").replace("?", "_")
        path = f"{path}_{safe_query}"
        
    if domain:
        full_path = f"{domain}/{path}"
    else:
        full_path = path
        
    # Replace characters that are not safe for filenames
    # We keep the dot in the domain if possible, but the path parts are usually joined by underscores
    filename = full_path.replace("/", "_")
    # We replace dots only if they are not the ones we want to keep (like in domain or extensions)
    # Actually, let's just replace all dots with underscores for maximum safety as before,
    # UNLESS the user specifically complained about the underscore version of the domain.
    # The user said "use the domain name". "raylib_com" is not the domain name. "raylib.com" is.
    # Let's try keeping dots.
    
    if not (filename.endswith(".html") or filename.endswith(".htm")):
        filename += ".html"
    return filename
