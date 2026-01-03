import os
import shutil
import plistlib
import httpx
from .index import DocsetIndex
from ..utils.url import get_filename_from_url, normalize_url, clean_domain
from urllib.parse import urlparse

class DocsetBuilder:
    def __init__(self, output_path, main_url=None, log_callback=None, verbose=False, force=False):
        self.docset_name = os.path.basename(output_path).replace(".docset", "")
        self.base_path = output_path
        self.contents_path = os.path.join(self.base_path, "Contents")
        self.resources_path = os.path.join(self.contents_path, "Resources")
        self.documents_path = os.path.join(self.resources_path, "Documents")
        
        self.index = DocsetIndex(os.path.join(self.resources_path, "docSet.dsidx"))
        self.verbose = verbose
        self.force = force
        self._setup_directories()
        self.first_page = None
        self.main_page = None
        self.main_url = normalize_url(main_url) if main_url else None
        self.main_domain = clean_domain(urlparse(main_url).netloc) if main_url else None
        self.all_pages = [] # List of (filename, url)
        self.has_icon = False
        self.log_callback = log_callback

    def log(self, message, verbose_only=False):
        if verbose_only and not self.verbose:
            return
        if self.log_callback:
            try:
                self.log_callback(message, verbose_only=verbose_only)
            except TypeError:
                self.log_callback(message)
        else:
            print(message)

    def _setup_directories(self):
        if os.path.exists(self.base_path):
            if self.force:
                self.log(f"Force building: removing existing docset at {self.base_path}")
                shutil.rmtree(self.base_path)
            else:
                # If NOT forcing, we might want to keep it? 
                # But DocsetBuilder currently ALWAYS rmtree's.
                # The user said "force build components". 
                # Let's keep the rmtree but log it if verbose.
                self.log(f"Cleaning output directory: {self.base_path}", verbose_only=True)
                shutil.rmtree(self.base_path)
        
        os.makedirs(self.documents_path)
        self.index.connect()

    async def set_icon(self, icon_url):
        if self.has_icon:
            return
        
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                r = await client.get(icon_url)
                if r.status_code == 200:
                    icon_path = os.path.join(self.base_path, "icon.png")
                    with open(icon_path, "wb") as f:
                        f.write(r.content)
                    self.has_icon = True
        except Exception as e:
            self.log(f"Failed to set icon: {e}")

    def add_page(self, parsed_page, url, is_main=False):
        filename = get_filename_from_url(url)
        self.log(f"Adding page: {url} as {filename}", verbose_only=True)
        self.all_pages.append((filename, url))
        
        # Check if this should be the main page
        if not self.main_page:
            if is_main:
                self.main_page = filename
            elif self.main_url and normalize_url(url) == self.main_url:
                self.main_page = filename
            
        if not self.first_page:
            self.first_page = filename
            
        dest_path = os.path.join(self.documents_path, filename)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(parsed_page.content)

        # Use page title for search index if it exists
        if parsed_page.title:
            self.index.add_entry(parsed_page.title, "Guide", filename)

        for name, type_, anchor in parsed_page.symbols:
            path = f"{filename}#{anchor}" if anchor else filename
            self.index.add_entry(name, type_, path)

    def finalize(self):
        index_file = self._write_info_plist()
        self._write_links_list()
        self.index.close()
        self.log(f"Docset finalized. Main page set to: {index_file}")

    def _write_links_list(self):
        links_file = self.base_path + ".links.txt"
        try:
            with open(links_file, "w", encoding="utf-8") as f:
                for filename, url in self.all_pages:
                    f.write(f"{filename}, {url}\n")
            self.log(f"Links list created at: {links_file}")
        except Exception as e:
            self.log(f"Failed to create links list: {e}")

    def _write_info_plist(self):
        index_file = self.main_page
        
        # If no explicit main page, look for candidates
        if not index_file:
            # 1. Look for index.html from the primary domain
            if self.main_domain:
                domain_index = f"{self.main_domain}_index.html"
                if os.path.exists(os.path.join(self.documents_path, domain_index)):
                    index_file = domain_index
            
            # 2. Look for FrontPage from the primary domain
            if not index_file and self.main_domain:
                for filename, _ in self.all_pages:
                    if filename.startswith(self.main_domain) and "FrontPage" in filename:
                        index_file = filename
                        break
            
            # 3. Look for ANY page from the primary domain
            if not index_file and self.main_domain:
                for filename, _ in self.all_pages:
                    if filename.startswith(self.main_domain):
                        index_file = filename
                        break

            # 4. Fallback to literal index.html
            if not index_file and os.path.exists(os.path.join(self.documents_path, "index.html")):
                index_file = "index.html"
            
            # 5. Fallback to the first page processed
            if not index_file:
                index_file = self.first_page or "index.html"

        info = {
            "CFBundleIdentifier": self.docset_name.lower(),
            "CFBundleName": self.docset_name,
            "DocSetPlatformFamily": self.docset_name.lower(),
            "isDashDocset": True,
            "dashIndexFilePath": index_file,
        }
        with open(os.path.join(self.contents_path, "Info.plist"), "wb") as f:
            plistlib.dump(info, f)
        return index_file
