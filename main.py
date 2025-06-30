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

# Function to install Playwright if missing
def install_playwright_if_missing():
    # When running as PyInstaller bundle, we need to set the browser path
    # to be inside our application directory
    if is_bundled():
        # Get the base directory of the bundled app
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        playwright_dir = os.path.join(base_dir, "_internal", "playwright", "driver", "package", ".local-browsers")
        
        # Set environment variables to tell Playwright where to find/install browsers
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = playwright_dir
        
        # Check if Chromium is already installed in our bundle
        if sys.platform == 'darwin':  # macOS
            browser_path = Path(playwright_dir) / "chromium-1169" / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
        else:  # Windows
            browser_path = Path(playwright_dir) / "chromium-1169" / "chrome-win" / "chrome.exe"
            
        if browser_path.exists():
            print(f"Playwright browser already installed at {browser_path}")
            return
    else:
        # For development environment, use default location based on platform
        if sys.platform == 'darwin':  # macOS
            home = os.path.expanduser("~")
            browser_path = Path(home) / "Library" / "Caches" / "ms-playwright" / "chromium-1169" / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
        else:  # Windows
            browser_path = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright" / "chromium-1169" / "chrome-win" / "chrome.exe"
            
        if browser_path.exists():
            print("Playwright browser already installed.")
            return
    
    print("Installing Playwright Chromium...")
    try:
        # Install only Chromium to save space
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True
        )
        print("Playwright installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install Playwright: {e}")
        sys.exit(1)

# Install Playwright if needed
install_playwright_if_missing()

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

# Import the leads server module - moved after GUI server starts
from src.leads.leads_server import main as start_leads_server

# Load environment variables - moved after GUI server starts
from src.utils.env_loader import load_environment

# Main function to start both servers
def main():
    # Start the GUI server first
    gui_thread = threading.Thread(target=start_gui_server)
    gui_thread.daemon = True
    gui_thread.start()
    
    # Wait a moment for GUI server to start
    time.sleep(1)
    
    # Open the browser
    webbrowser.open('http://localhost:8080')
    
    # Now load environment variables
    env_loaded = load_environment()
    if not env_loaded:
        print("Warning: Some environment variables are missing. Please configure them through the GUI.")
    
    # Start the leads server in a separate thread
    leads_thread = threading.Thread(target=start_leads_server)
    leads_thread.daemon = True
    leads_thread.start()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        sys.exit(0)

if __name__ == "__main__":
    main()