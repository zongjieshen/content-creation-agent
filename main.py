import os
import sys
import threading
import webbrowser
import time
import subprocess
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our resource path and environment loader utilities
from src.utils.resource_path import get_resource_path, is_bundled

def install_playwright_if_missing():
    """Set up Playwright Chromium browser path. No install in bundled mode or Docker."""
    # Skip Playwright installation in Docker
    if os.environ.get('DOCKER_ENV') == 'true':
        print("Docker mode: Skipping Playwright installation")
        return
        
    if is_bundled():
        # Onefile .exe extraction directory (e.g., _MEIPASS)
        browser_dir = get_resource_path("_internal/playwright/driver/package/.local-browsers")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browser_dir
        print(f"Bundled mode: PLAYWRIGHT_BROWSERS_PATH set to {browser_dir}")
        return  # ✅ Skip any install or browser_path check

    # Dev mode — check if Playwright is already installed
    if sys.platform == 'darwin':
        home = os.path.expanduser("~")
        browser_path = Path(home) / "Library/Caches/ms-playwright/chromium-1169/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
    else:
        browser_path = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright/chromium-1169/chrome-win/chrome.exe"

    if browser_path.exists():
        print(f"Playwright browser already installed at {browser_path}")
        return

    # Dev only: install if missing
    print("Installing Playwright Chromium...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("Playwright installed successfully.")


# Simple HTTP server for serving the GUI files
class GUIServer(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=get_resource_path('gui'), **kwargs)

# Start the GUI server
def start_gui_server():
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, GUIServer)
    print(f"GUI server started at http://localhost:8080")
    httpd.serve_forever()

# Import server modules
from src.leads.server import main as start_leads_server
from src.scraping.server import main as start_scraping_server
from src.captions.server import main as start_captions_server
from src.utils.env_loader import load_environment

def main():
    # Start the GUI server first
    gui_thread = threading.Thread(target=start_gui_server)
    gui_thread.daemon = True
    gui_thread.start()

    time.sleep(1)  # Wait for GUI to start
    webbrowser.open('http://localhost:8080')

    env_loaded = load_environment()
    if not env_loaded:
        print("Warning: Some environment variables are missing. Please configure them through the GUI.")

    leads_thread = threading.Thread(target=start_leads_server)
    leads_thread.daemon = True
    leads_thread.start()

    scraping_thread = threading.Thread(target=start_scraping_server)
    scraping_thread.daemon = True
    scraping_thread.start()

    captions_thread = threading.Thread(target=start_captions_server)
    captions_thread.daemon = True
    captions_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        sys.exit(0)

if __name__ == "__main__":
    install_playwright_if_missing()
    main()
