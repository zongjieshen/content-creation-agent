# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Get the path to the Playwright browsers based on platform
# This is where Playwright will install browsers by default
if sys.platform == 'darwin':  # macOS
    home = os.path.expanduser("~")
    playwright_path = os.path.join(home, "Library", "Caches", "ms-playwright")
else:  # Windows
    playwright_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")

# Create a list of browser binaries to include
playwright_browsers = []
if os.path.exists(playwright_path):
    for browser_type in os.listdir(playwright_path):
        if browser_type.startswith("chromium"):
            browser_dir = os.path.join(playwright_path, browser_type)
            # Include the entire browser directory
            playwright_browsers.append(
                (browser_dir, f'playwright/driver/package/.local-browsers/{browser_type}')
            )

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=playwright_browsers,  # Include Playwright browser binaries
    datas=[
        ('gui', 'gui'),  # Include the GUI directory
        ('src', 'src'),   # Include the src directory
        ('config.yaml', '.'),  # Include the config file
        # Removed .env file dependency
    ],
    hiddenimports=['playwright.sync_api', 'playwright.async_api'],  # Add Playwright to hidden imports
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
    [],
    exclude_binaries=True,
    name='content-create-agent',
    debug=True,  # Enable debug mode to get more information
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # This is already set to True, which is good
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='content-create-agent',
)
