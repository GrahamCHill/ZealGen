# Frontpage Handling

The frontpage of a generated docset is the page that opens when you select the docset in Zeal or Dash. This is defined by the `dashIndexFilePath` key in the `Contents/Info.plist` file.

In DocuGen, this is handled in `src/docugen/docset/builder.py` within the `_write_info_plist` method.

## How the Frontpage is Determined

DocuGen uses a series of heuristics to find the best candidate for the frontpage if one hasn't been explicitly set:

1.  **Explicit Main Page**: If a page was added with `is_main=True` or its URL matches the `main_url` passed to the `DocsetBuilder`, it is used as the main page.
2.  **Domain Index**: It looks for a file named `{domain}_index.html` (where `{domain}` is the primary domain of the documentation).
3.  **FrontPage heuristic**: It searches for any filename from the primary domain that contains "FrontPage".
4.  **Primary Domain Fallback**: It uses the first page found that belongs to the primary domain.
5.  **`index.html`**: It checks for a literal `index.html` file in the root of the documents.
6.  **First Page**: As a final fallback, it uses the first page that was processed during the generation.

## Code Reference

The logic is implemented in `DocsetBuilder._write_info_plist`:

```python
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
        
        # ... (further fallbacks)
```

The resulting `Info.plist` contains:
```xml
<key>dashIndexFilePath</key>
<string>chosen_index_file.html</string>
```
