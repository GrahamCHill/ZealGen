# -*- mode: python ; coding: utf-8 -*-

import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# -------------------------------------------------
# Collect Qt (PySide6)
# -------------------------------------------------
qt_datas, qt_binaries, qt_hidden = collect_all("PySide6")

# -------------------------------------------------
# Collect Playwright (python side)
# Browsers are NOT bundled (see note below)
# -------------------------------------------------
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

hiddenimports = (
    qt_hidden
    + pw_hidden
    + [
        # dynamic imports in your codebase
        "playwright.sync_api",
        "playwright.async_api",

        # your internal modules (defensive)
        "app",
        "cli",
        "core",
        "fetch.base",
        "fetch.httpx_fetcher",
        "fetch.playwright_fetcher",
        "fetch.qt_fetcher",
        "parsers.base",
        "parsers.docusaurus",
        "parsers.generic",
        "parsers.rustdoc",
        "parsers.sphinx",
        "utils.url",
        "utils.hashing",
    ]
)

datas = (
    qt_datas
    + pw_datas
    + [
        # bundle non-python assets
        ("assets", "assets"),
    ]
)

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=qt_binaries + pw_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="zealgen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # <-- app bundle, no terminal
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ZealGen",
)

app = BUNDLE(
    coll,
    name="zealgen.app",
    icon=None,  # set .icns later if you want
    bundle_identifier="com.yourname.zealgen",
)
