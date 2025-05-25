# C:/Users/obsid/Desktop/AI Projects/Voidframe_0.3/core/env.py
import os
import sys
from pathlib import Path # Import the Path object

# Determine the root directory based on whether the script is frozen (PyInstaller) or not.
# Ensure ROOT_DIR is a pathlib.Path object.
if getattr(sys, 'frozen', False):  # Running as an .exe file
    ROOT_DIR = Path(os.path.dirname(sys.executable)).resolve()
else: # Running as a standard .py script
    # Go up one level from the 'core' directory where this file resides
    ROOT_DIR = Path(os.path.dirname(__file__)).parent.resolve()

# Optional: Add a check or print statement for debugging
# print(f"ROOT_DIR determined as: {ROOT_DIR} (Type: {type(ROOT_DIR)})")