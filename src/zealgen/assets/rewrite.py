from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import httpx
import pathlib
import hashlib


import re

async def rewrite_assets(html, base_url, out_dir):
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
                        
                        local_name = await download_and_save_asset(client, absolute_url, out_dir, tag)
                        if local_name:
                            new_srcset = new_srcset.replace(img_url, local_name)
                    
                    el[attr] = new_srcset
                    continue

                absolute_url = urljoin(base_url, attr_value)
                if not absolute_url.startswith("http"):
                    continue

                local_name = await download_and_save_asset(client, absolute_url, out_dir, tag)
                if local_name:
                    el[attr] = local_name

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

    return str(soup)

async def download_and_save_asset(client, url, out_dir, tag):
    try:
        r = await client.get(url)
        r.raise_for_status()
        data = r.content
        
        # Use a hash of the full URL to ensure uniqueness and avoid collision
        ext = pathlib.Path(url).suffix
        if not ext or len(ext) > 5:
            if tag == "script":
                ext = ".js"
            elif tag == "link":
                ext = ".css"
            else:
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
                else:
                    ext = ".png" # Default for images
        
        fname = hashlib.md5(url.encode()).hexdigest() + ext
        
        path = out_dir / fname
        if not path.exists():
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
