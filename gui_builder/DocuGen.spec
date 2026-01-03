# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('/Users/grahamhill/Projects/Code/docsetGenerator/src/docugen', 'docugen'), ('/Users/grahamhill/Library/Caches/ms-playwright', 'ms-playwright')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['/Users/grahamhill/Projects/Code/docsetGenerator/src/docugen/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DocuGen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity='-',
    entitlements_file=None,
    icon=['/Users/grahamhill/Projects/Code/docsetGenerator/gui_builder/assets/icon.icns'],
)
app = BUNDLE(
    exe,
    name='DocuGen.app',
    icon='/Users/grahamhill/Projects/Code/docsetGenerator/gui_builder/assets/icon.icns',
    bundle_identifier='com.yourdomain.docugen',
)
