import os
import sys
import platform

# Determine if we're running in a PyInstaller bundle
def is_bundled():
    return getattr(sys, 'frozen', False)

# Determine if we're running in a Docker container
def is_docker():
    """Check if running in Docker environment"""
    return os.environ.get('DOCKER_ENV', 'false').lower() == 'true'

# Get the directory containing our files
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev, PyInstaller, and Docker"""
    if is_bundled():
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app 
        # path into variable _MEIPASS
        base_path = sys._MEIPASS
    elif is_docker():
        # In Docker, use the mounted volumes
        if relative_path == "config.yaml" or relative_path.startswith("config/"):
            # Config files are mounted to /app/config
            return os.path.join("/app", "config", relative_path.replace("config/", "", 1) if relative_path.startswith("config/") else relative_path)
        elif relative_path.startswith("data/"):
            # Data files are mounted to /app/data
            return os.path.join("/app", "data", relative_path.replace("data/", "", 1))
        elif relative_path.startswith("uploads/"):
            # Upload files are mounted to /app/uploads
            return os.path.join("/app", "uploads", relative_path.replace("uploads/", "", 1))
        else:
            # Default to app root for other files
            return os.path.join("/app", relative_path)
    else:
        # Development environment - use project root
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    return os.path.join(base_path, relative_path)

# Get the app data directory for storing persistent data
def get_app_data_dir(app_name="content-creation-agent"):
    """Get the appropriate app data directory based on the operating system and environment
    
    Args:
        app_name (str): The name of the application folder
        
    Returns:
        str: Path to the app data directory
    """
    if is_docker():
        # In Docker, use the mounted data directory
        return "/app/data"
    
    system = platform.system()
    
    if system == "Windows":
        # Use %APPDATA% on Windows (typically C:\Users\Username\AppData\Roaming)
        app_data = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming")), app_name)
    elif system == "Darwin":  # macOS
        # Use ~/Library/Application Support on macOS
        app_data = os.path.join(os.path.expanduser("~/Library/Application Support"), app_name)
    else:  # Linux and others
        # Use ~/.local/share on Linux
        app_data = os.path.join(os.path.expanduser("~/.local/share"), app_name)
    
    # Create the directory if it doesn't exist
    os.makedirs(app_data, exist_ok=True)
    
    return app_data