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
    
    path = parsed.path
    # Remove common index files
    for index_file in ["/index.html", "/index.htm", "/index.php", "/index.jsp", "/index.asp"]:
        if path.lower().endswith(index_file):
            path = path[:-len(index_file)]
            break

    path = path.rstrip("/")
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

def get_base_domain(domain: str) -> str:
    """Get the base domain (e.g. example.com from sub.example.com).
    This is a simple version that might not handle all TLDs correctly
    but works for common ones like .org, .com, .net."""
    parts = domain.split(".")
    if len(parts) >= 2:
        # Check for common two-part TLDs like .co.uk
        if len(parts) >= 3 and parts[-2] in ["co", "com", "org", "net", "edu", "gov"]:
             return ".".join(parts[-3:])
        return ".".join(parts[-2:])
    return domain

def get_filename_from_url(url: str) -> str:
    # Normalize the URL first to handle index files consistently
    parsed = urlparse(url)
    domain = clean_domain(parsed.netloc)
    
    path = parsed.path
    
    # Standardize path: remove common index files to be consistent with normalize_url
    for index_file in ["/index.html", "/index.htm", "/index.php", "/index.jsp", "/index.asp"]:
        if path.lower().endswith(index_file):
            path = path[:-len(index_file)]
            break

    # If it ends with / or is empty, it's definitely an index page
    if not path or path.endswith("/"):
        if not path.endswith("/"):
            path += "/"
        path += "index.html"
    elif "." not in path.split("/")[-1]:
        # If no extension in the last part of path, we treat it as a directory
        # to be consistent with the trailing slash case, since normalize_url
        # treats them the same. 
        # Most documentation tools (Sphinx, Docusaurus) use directories for clean URLs.
        path += "/index.html"
    
    # Remove leading slash
    if path.startswith("/"):
        path = path[1:]
    
    if not path:
        path = "index.html"
    
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
    
    # If it's a root domain without a path, it might end up being just "domain"
    # we want to ensure it has .html if it's meant to be a page.
    if not (filename.endswith(".html") or filename.endswith(".htm")):
        filename += ".html"
    
    # Check if the filename is literally "index.html" (which shouldn't happen with domain prepended)
    # or if it's the domain's index. 
    # The user might prefer a cleaner "index.html" for the main page.
    # But for now, consistency is better.
    
    return filename
