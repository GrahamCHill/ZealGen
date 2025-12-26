# ZealGen

ZealGen is a powerful, Python-based tool designed to generate [Zeal](https://zealdocs.org/) (and Dash) compatible docsets from any website or online documentation. It features a modern Qt6-based GUI and a versatile CLI, with built-in support for modern, JavaScript-heavy documentation sites.

## Features

- **Initial URL Scan**: Automatically discovers reachable links and subdomains before starting the full generation.
- **Granular URL Selection**: A two-pane selection dialog allows you to choose exactly which subpages or external links to include in your final docset.
- **Multiple JS Rendering Engines**:
    - **Playwright**: Uses Chromium for heavy-duty, accurate rendering of complex web apps.
    - **QtWebEngine**: A built-in, lightweight alternative using PySide6's native WebEngine, featuring "Stability Polling" to ensure dynamic content is fully loaded.
- **Smart Asset Handling**: Downloads and localizes CSS, JS, images (including `srcset` and CSS `url()` references), and favicons.
- **Built-in Parsers**: Specialized parsers for common documentation formats:
    - Sphinx
    - Docusaurus
    - Rustdoc
    - Generic HTML (with smart title and symbol extraction)
- **Robustness**: Automatic retries with exponential backoff for network-resilient fetching.
- **Clean Naming**: Generates clean, human-readable filenames and docset names, automatically stripping redundant `www.` and TLDs while preserving the core domain identity.

## Installation

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/youruser/docsetGenerator.git
   cd docsetGenerator
   ```

2. Install dependencies:
   ```bash
   uv sync
   # OR
   pip install .
   ```

3. (Optional) If you plan to use the Playwright engine:
   ```bash
   playwright install chromium
   ```

## Usage

### GUI Mode

To launch the graphical interface, simply run the main entry point without arguments:

```bash
zealgen
```

1. **Enter URLs**: Provide one or more base documentation URLs.
2. **Configure Options**: Choose your JS engine (Playwright, Qt, or None for static sites) and set the maximum page limit.
3. **Scan**: Click "Generate Docset" to perform an initial scan.
4. **Select**: Use the two-pane dialog to include/exclude discovered subpages.
5. **Save**: Choose your output destination (it will automatically suggest a `.docset` name).

### CLI Mode

For automation, you can use the command-line interface:

```bash
zealgen https://docs.python.org/3/ --out Python.docset --js --max-pages 500
```

#### CLI Options:
- `urls`: One or more source URLs.
- `--out`: Path to the output `.docset` directory.
- `--js`: Enable JavaScript rendering (uses Playwright by default).
- `--max-pages`: Maximum number of pages to crawl (default: 100).

## Technical Details

### Project Structure

- `src/zealgen/core.py`: The main orchestration logic for scanning and generation.
- `src/zealgen/app.py`: PySide6 implementation of the GUI.
- `src/zealgen/fetch/`: Modular fetcher system (HTTPX, Playwright, QtWebEngine).
- `src/zealgen/parsers/`: Logic for identifying symbols and structure in different doc formats.
- `src/zealgen/assets/`: Asset discovery and rewriting engine.
- `src/zealgen/docset/`: Builder for the `.docset` folder structure and SQLite index.

### Development and Testing

The project uses `pytest` for unit testing.

```bash
PYTHONPATH=src python3 -m unittest discover tests
```

## License

[Specify License Here - e.g., MIT]
