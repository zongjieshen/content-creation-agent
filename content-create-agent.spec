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
#playwright_browsers = []
#if os.path.exists(playwright_path):
#    for browser_type in os.listdir(playwright_path):
#        if browser_type.startswith("chromium"):  # ✅ only Chromium
#            browser_dir = os.path.join(playwright_path, browser_type)
#            playwright_browsers.append(
#                (browser_dir, f'_internal/playwright/driver/package/.local-browsers/{browser_type}')
#            )

a = Analysis(
    ['main.py'],
    pathex=[],
    #binaries=playwright_browsers,
    datas=[
        ('gui', 'gui'),
        ('src', 'src'),
        ('config.yaml', '.'),
    ],
    hiddenimports=[
        # Web framework and API dependencies
        'fastapi',
        'uvicorn',
        'pydantic',
        'starlette',
        'python-multipart',
        
        # HTTP and networking
        'httpx',
        
        # AI and language processing
        'google.generativeai',
        'google.genai',
        'langgraph',
        
        # Web scraping and browser automation
        'playwright.sync_api',
        'playwright.async_api',
        'playwright._impl._driver',
        
        # Data processing and storage
        'numpy',
        'faiss',
        'faiss.swigfaiss',
        
        # Security and sanitization
        'bleach',
        
        # Configuration and environment
        'dotenv',
        'yaml',
        
        # Utilities
        'trendspy',
        
        # Core modules used in the application
        'asyncio',
        'threading',
        'webbrowser',
        'uuid',
        'json',
        'hashlib',
        'logging',
        'traceback',
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
        #'pandas',  # Added to excludes if not needed
        'pillow',  # Added to excludes if not needed
        'pytest',  # Added to excludes if not needed
        'sphinx',  # Added to excludes if not needed
        'jupyter',  # Added to excludes if not needed
        'notebook',  # Added to excludes if not needed
        'sympy',  # Added to excludes if not needed
        'spacy',  # Added to excludes if not needed
        'h5py',  # Added to excludes if not needed
        'numba',  # Added to excludes if not needed
        'bokeh',  # Added to excludes if not needed
        'seaborn',  # Added to excludes if not needed
        'dask',  # Added to excludes if not needed
    ],
    noarchive=False,
    optimize=0, 
)

# ✅ Exclude unnecessary files from the bundle
def exclude_files(file_list):
    return [file for file in file_list if not (
        # Exclude test files
        "__pycache__" in file[0] or
        "tests" in file[0] or
        "test_" in file[0] or
        # Exclude documentation
        "docs" in file[0] or
        "examples" in file[0] or
        "tutorials" in file[0] or
        # Exclude development files
        ".git" in file[0] or
        ".github" in file[0]
    )]

a.datas = exclude_files(a.datas)

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
    upx=False,     # ✅ Compress with UPX (requires UPX installed)
    upx_exclude=[],  # ✅ Exclude problematic files from UPX compression
    runtime_tmpdir=None,  # ✅ Use memory instead of disk for temporary files
    console=True,  # Set to False if GUI-only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add an icon file path here if you have one
)
