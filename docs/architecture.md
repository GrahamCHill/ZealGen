# Architecture

DocuGen is organized into several modules:

- `docugen.app`: The PySide6-based GUI application.
- `docugen.cli`: The command-line interface.
- `docugen.core`: Core logic for scanning and generating docsets.
- `docugen.fetch`: Fetchers for retrieving web content (HTTPX, Playwright, Qt).
- `docugen.parsers`: Parsers for extracting content and symbols from different doc formats.
- `docugen.docset`: Tools for building the final `.docset` structure, including the SQLite index and `Info.plist`.
- `docugen.assets`: Logic for rewriting asset URLs to local paths.

## Generation Flow

1. **Initialization**: `DocsetBuilder` sets up the directory structure.
2. **Scanning/Fetching**: `core.scan` or `core.generate` fetches URLs using the selected `Fetcher`.
3. **Parsing**: Content is passed through parsers to extract symbols and clean up HTML.
4. **Asset Rewriting**: External assets are downloaded and linked locally.
5. **Indexing**: Symbols are added to the `DocsetIndex` (SQLite database).
6. **Finalization**: `Info.plist` is generated, and the database is closed.
