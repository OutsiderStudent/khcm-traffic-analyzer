# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["arterial_launcher.py"],
    pathex=["src"],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=["openpyxl", "openpyxl.styles", "pythoncom", "pywintypes", "win32com", "win32com.client", "win32timezone"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

a.binaries = type(a.binaries)(
    item for item in a.binaries
    if not item[0].lower().startswith(("api-ms-win-", "ext-ms-win-", "icu"))
    and item[0].lower() != "ucrtbase.dll"
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="도시교외간선도로분석_v1.8.1",
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
    icon=["assets/arterial-analysis-icon.ico"],
)
