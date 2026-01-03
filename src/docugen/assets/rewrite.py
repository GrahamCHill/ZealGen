from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import httpx
import pathlib
import hashlib


import re

async def rewrite_assets(html, base_url, out_dir, force=False, verbose=False, log_callback=None):
    def log(msg):
        if verbose:
            if log_callback:
                try:
                    log_callback(msg, verbose_only=True)
                except TypeError:
                    log_callback(msg)
            else:
                print(msg)

    soup = BeautifulSoup(html, "lxml")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Define tags and their attributes that point to assets
        asset_targets = [
            ("link", "href"),
            ("script", "src"),
            ("img", "src"),
            ("source", "src"),
            ("source", "srcset"),
            ("img", "srcset"),
            ("input", "src"),
        ]
        
        for tag, attr in asset_targets:
            for el in soup.find_all(tag):
                if not el.get(attr):
                    continue
                
                if tag == "input" and el.get("type") != "image":
                    continue

                attr_value = el[attr]
                
                # Handle srcset which can contain multiple URLs
                if attr == "srcset":
                    urls_in_srcset = []
                    parts = attr_value.split(",")
                    for part in parts:
                        part = part.strip()
                        if not part: continue
                        subparts = part.split()
                        if not subparts: continue
                        img_url = subparts[0]
                        urls_in_srcset.append((part, img_url))
                    
                    new_srcset = attr_value
                    for full_part, img_url in urls_in_srcset:
                        absolute_url = urljoin(base_url, img_url)
                        if not absolute_url.startswith("http"):
                            continue
                        
                        local_name = await download_and_save_asset(client, absolute_url, out_dir, tag, force=force, verbose=verbose, log_callback=log_callback)
                        if local_name:
                            new_srcset = new_srcset.replace(img_url, local_name)
                    
                    el[attr] = new_srcset
                    continue

                absolute_url = urljoin(base_url, attr_value)
                if not absolute_url.startswith("http"):
                    continue

                local_name = await download_and_save_asset(client, absolute_url, out_dir, tag, force=force, verbose=verbose, log_callback=log_callback)
                if local_name:
                    el[attr] = local_name
                    # If it's a CSS file, we need to rewrite assets inside it
                    if tag == "link" and el.get("rel") == ["stylesheet"] or (local_name.endswith(".css")):
                         await rewrite_css_assets(client, out_dir / local_name, absolute_url, out_dir, force=force, verbose=verbose, log_callback=log_callback)

        # ES modules imports in script tags
        for script in soup.find_all("script", type="module"):
            if script.string:
                content = script.string
                # Simple regex for static imports: import ... from '...'
                # We need to handle ../ and other relative paths
                imports = re.findall(r'from\s+[\'"](.+?)[\'"]', content)
                direct_imports = re.findall(r'import\s+[\'"](.+?)[\'"]', content)
                
                for imp_url in set(imports + direct_imports):
                    if imp_url.startswith("data:"): continue
                    
                    # Resolve relative URL using current page URL
                    # However, rewrite_assets' base_url IS the current page URL (usually)
                    absolute_url = urljoin(base_url, imp_url)
                    if not absolute_url.startswith("http"): continue
                    
                    local_name = await download_and_save_asset(client, absolute_url, out_dir, "script", force=force, verbose=verbose, log_callback=log_callback)
                    if local_name:
                        # Use local_name instead of imp_url
                        # We MUST ensure we only replace the exact string in quotes to avoid partial matches
                        # but simple string replace is risky if imp_url is short.
                        # However, ES module imports are usually specific enough.
                        content = content.replace(f"'{imp_url}'", f"'{local_name}'")
                        content = content.replace(f'"{imp_url}"', f'"{local_name}"')
                script.string = content

        # Common JS asset patterns
        for script in soup.find_all("script"):
            if script.string:
                content = script.string
                # Match fetch('...') or fetch("...")
                fetches = re.findall(r'fetch\(\s*[\'"](.+?)[\'"]\s*\)', content)
                # Also match other common dynamic loading patterns (e.g. THREE.FileLoader)
                dynamic_loads = re.findall(r'[\'"](.+?\.(?:glb|gltf|obj|mtl|hdr|json|png|jpg|jpeg|webp|mp4|webm|svg|woff2?|ttf|otf|wasm))[\'"]', content)
                
                for asset_url in set(fetches + dynamic_loads):
                    if asset_url.startswith("data:"): continue
                    
                    absolute_url = urljoin(base_url, asset_url)
                    if not absolute_url.startswith("http"): continue
                    
                    ext = pathlib.Path(asset_url.split("?")[0]).suffix.lower()
                    tag_type = "json" if ext == ".json" else "asset"
                    local_name = await download_and_save_asset(client, absolute_url, out_dir, tag_type, force=force, verbose=verbose, log_callback=log_callback)
                    if local_name:
                        content = content.replace(f"'{asset_url}'", f"'{local_name}'")
                        content = content.replace(f'"{asset_url}"', f'"{local_name}"')
                script.string = content

        # Handle YouTube embeds in iframes
        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            if "youtube.com/embed/" in src or "youtube-nocookie.com/embed/" in src:
                # Keep absolute URL for YouTube
                if "youtube.com/embed/" in src:
                    video_id = src.split("youtube.com/embed/")[1].split("?")[0]
                else:
                    video_id = src.split("youtube-nocookie.com/embed/")[1].split("?")[0]
                
                youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                
                # Create a link to the video
                link = soup.new_tag("a", href=youtube_url, target="_blank")
                link.string = "View on YouTube"
                
                # Add a container or just append the link after the iframe
                container = soup.new_tag("div", **{"class": "youtube-embed-container"})
                iframe.wrap(container)
                
                link_div = soup.new_tag("div", **{"class": "youtube-link"})
                link_div.append(link)
                container.append(link_div)
            else:
                # Ensure other iframes use absolute URLs if they are not already
                # This prevents relative path issues when the page is served from a docset
                absolute_url = urljoin(base_url, src)
                iframe["src"] = absolute_url

        # Remove "xr-spatial-tracking" from any Permissions-Policy meta tags if they exist
        for meta in soup.find_all("meta", attrs={"http-equiv": "Permissions-Policy"}):
            if "xr-spatial-tracking" in meta.get("content", ""):
                meta["content"] = meta["content"].replace("xr-spatial-tracking", "")

        # Handle style attributes with url()
        for el in soup.find_all(style=True):
            style = el["style"]
            urls = re.findall(r'url\([\'"]?(.*?)[\'"]?\)', style)
            for url in urls:
                if url.startswith("data:"):
                    continue
                absolute_url = urljoin(base_url, url)
                if not absolute_url.startswith("http"):
                    continue
                
                local_name = await download_and_save_asset(client, absolute_url, out_dir, "style")
                if local_name:
                    style = style.replace(url, local_name)
            el["style"] = style

        # Handle inline event handlers like onmouseover/onmouseout attributes
        event_handlers = ["onmouseover", "onmouseout", "onclick", "onload"]
        for handler in event_handlers:
            for el in soup.find_all(attrs={handler: True}):
                content = el[handler]
                # Match both absolute paths and relative paths that look like assets
                # Also handle potentially quoted URLs inside the handler string
                urls = re.findall(r'[\'"]([^\'"]+?\.(?:png|jpg|jpeg|webp|gif|svg|mp4|webm|js|css))[\'"]', content)
                for url in set(urls):
                    if url.startswith("data:"): continue
                    absolute_url = urljoin(base_url, url)
                    if not absolute_url.startswith("http"):
                        continue
                    
                    ext = pathlib.Path(url.split("?")[0]).suffix.lower()
                    tag_type = "img" if ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"] else "asset"
                    
                    local_name = await download_and_save_asset(client, absolute_url, out_dir, tag_type)
                    if local_name:
                        # Ensure we only replace the exact URL inside quotes
                        content = content.replace(f"'{url}'", f"'{local_name}'")
                        content = content.replace(f'"{url}"', f'"{local_name}"')
                el[handler] = content

    return str(soup)

async def rewrite_css_assets(client, css_path, base_url, out_dir, force=False, verbose=False, log_callback=None):
    if not css_path.exists():
        return
    
    def log(msg):
        if verbose:
            if log_callback:
                try:
                    log_callback(msg, verbose_only=True)
                except TypeError:
                    log_callback(msg)
            else:
                print(msg)

    content = css_path.read_text(errors='ignore')
    # Find url(...) in CSS
    urls = re.findall(r'url\([\'"]?(.*?)[\'"]?\)', content)
    modified = False
    for url in set(urls):
        if url.startswith("data:") or url.startswith("http"):
            absolute_url = urljoin(base_url, url)
        else:
            absolute_url = urljoin(base_url, url)
        
        if not absolute_url.startswith("http"):
            continue
            
        local_name = await download_and_save_asset(client, absolute_url, out_dir, "style", force=force, verbose=verbose, log_callback=log_callback)
        if local_name:
            content = content.replace(url, local_name)
            modified = True
    
    if modified:
        css_path.write_text(content)

async def download_and_save_asset(client, url, out_dir, tag, force=False, verbose=False, log_callback=None):
    def log(msg):
        if verbose:
            if log_callback:
                try:
                    log_callback(msg, verbose_only=True)
                except TypeError:
                    log_callback(msg)
            else:
                print(msg)
    try:
        # Avoid re-downloading
        ext = pathlib.Path(url.split("?")[0]).suffix
        if not ext or len(ext) > 5:
            if tag == "script":
                ext = ".js"
            elif tag == "link":
                ext = ".css"
            elif tag == "json":
                ext = ".json"
            else:
                ext = "" # Will be guessed from content-type
        
        fname = hashlib.md5(url.encode()).hexdigest() + ext
        path = out_dir / fname
        if path.exists() and not force:
            return fname

        if force and path.exists():
            log(f"Force re-downloading asset: {url}")
        else:
            log(f"Downloading asset: {url}")

        r = await client.get(url)
        r.raise_for_status()
        data = r.content
        
        if not ext:
            # Try to guess from content-type
            content_type = r.headers.get("content-type", "")
            if "image/svg" in content_type:
                ext = ".svg"
            elif "image/jpeg" in content_type:
                ext = ".jpg"
            elif "image/gif" in content_type:
                ext = ".gif"
            elif "image/webp" in content_type:
                ext = ".webp"
            elif "application/json" in content_type:
                ext = ".json"
            elif "font/woff2" in content_type:
                ext = ".woff2"
            elif "font/woff" in content_type:
                ext = ".woff"
            elif "font/ttf" in content_type:
                ext = ".ttf"
            else:
                ext = ".png" # Default for images
            
            # Recompute filename with extension if we didn't have one
            fname = hashlib.md5(url.encode()).hexdigest() + ext
            path = out_dir / fname
            if path.exists():
                return fname

        path.write_bytes(data)
        return fname
    except Exception as e:
        print(f"Failed to download asset {url}: {e}")
        return None

def get_favicon_url(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    # Look for common favicon patterns
    icon_link = soup.find("link", rel=lambda x: x and "icon" in x.lower())
    if icon_link and icon_link.get("href"):
        return urljoin(base_url, icon_link["href"])
    
    # Fallback to /favicon.ico on the same domain
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
