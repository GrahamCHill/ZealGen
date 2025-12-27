# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# -------------------------------------------------
# Playwright (python side only)
# -------------------------------------------------
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

hiddenimports = (
    pw_hidden
    + [
        "playwright.sync_api",
        "playwright.async_api",

        # internal dynamic imports
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
    pw_datas
    + [
        ("assets", "assets"),
    ]
)

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=pw_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    console=False,  # macOS app bundle
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="zealgen",
)

app = BUNDLE(
    coll,
    name="ZealGen.app",
    icon = None, # set .icns later if you want
    bundle_identifier="dev.grahamhill.zealgen",
)
