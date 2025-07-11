import os
import sys

# Determine if we're running in a PyInstaller bundle
def is_bundled():
    return getattr(sys, 'frozen', False)

# Get the directory containing our files
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if is_bundled():
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app 
        # path into variable _MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    return os.path.join(base_path, relative_path)