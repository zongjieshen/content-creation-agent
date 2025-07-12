# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Limit to only Chromium browser (skip webkit/firefox)
if sys.platform == 'darwin':
    home = os.path.expanduser("~")
    playwright_path = os.path.join(home, "Library", "Caches", "ms-playwright")
else:
    playwright_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")

# ✅ Bundle only Chromium (reduce bulk)
playwright_browsers = []
if os.path.exists(playwright_path):
    for browser_type in os.listdir(playwright_path):
        if browser_type.startswith("chromium"):  # ✅ only Chromium
            browser_dir = os.path.join(playwright_path, browser_type)
            playwright_browsers.append(
                (browser_dir, f'_internal/playwright/driver/package/.local-browsers/{browser_type}')
            )

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=playwright_browsers,
    datas=[
        ('gui', 'gui'),
        ('src', 'src'),
        ('config.yaml', '.'),
        ('data', 'data'),
    ],
    hiddenimports=[
        'playwright.sync_api',
        'playwright.async_api',
        'playwright._impl._driver',  # ✅ ensure driver loads
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ❌ Remove large unused libraries
        'tkinter',
        'matplotlib',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'IPython',
        'scipy',
        'pydub',
        'torch',
        'tensorflow',
        'sklearn',
        'cv2',
        'nltk',
    ],
    noarchive=False,
    optimize=2,  # ✅ Optimize to level 2
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='content-create-agent',
    debug=False,  # ✅ Turn off debug for smaller size
    bootloader_ignore_signals=False,
    strip=True,   # ✅ Strip debug symbols
    upx=True,     # ✅ Compress with UPX (requires UPX installed)
    console=True,  # Set to False if GUI-only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
