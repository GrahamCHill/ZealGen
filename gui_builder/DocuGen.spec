# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/Users/grahamhill/Projects/Code/docsetGenerator/src/docugen/main.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/grahamhill/Projects/Code/docsetGenerator/src/docugen', 'docugen')],
    hiddenimports=[],
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
    codesign_identity=None,
    entitlements_file=None,
    icon=['/Users/grahamhill/Projects/Code/docsetGenerator/gui_builder/assets/icon.icns'],
)
app = BUNDLE(
    exe,
    name='DocuGen.app',
    icon='/Users/grahamhill/Projects/Code/docsetGenerator/gui_builder/assets/icon.icns',
    bundle_identifier='com.yourdomain.docugen',
)
