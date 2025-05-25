import os
import base64
from google.genai import types
from google import genai
import json
from core.env import ROOT_DIR  # Import ROOT_DIR

# Load the Gemini-specific config file once from the same directory.
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    """Loads the Gemini API-specific configuration."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def process_files(file_list, api_config):
    """
    Processes a list of file names using the Gemini config file.
    - Uses `base64_upload_threshold` from config.json.
    - Uses `mime_types` from config.json.
    - Builds the upload directory relative to the main Voidframe folder.
    """
    processed_parts = []
    
    # Load the local Gemini config.
    config = load_config()
    
    # Retrieve the file size threshold (default: 20MB if not specified)
    threshold = config.get("base64_upload_threshold", 20 * 1024 * 1024)
    
    # Retrieve MIME type mappings from config.json; fallback to defaults if not provided.
    mime_types = config.get("mime_types", {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif"
    })
    
    # Build the upload directory path.
    # Instead of going up from __file__, use ROOT_DIR.
    upload_dir = os.path.join(ROOT_DIR, "storage", "file_upload")
    upload_dir = os.path.abspath(upload_dir)
    
    # Initialize the Gemini client using the GEMINI_API_KEY environment variable.
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    client = genai.Client(api_key=gemini_api_key)
    
    for filename in file_list:
        file_path = os.path.join(upload_dir, filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File '{filename}' not found in the upload directory.")
        
        file_size = os.path.getsize(file_path)
        ext = os.path.splitext(filename)[1].lower()
        # Look up MIME type from the mapping; default to generic binary if not found.
        mime_type = mime_types.get(ext, "application/octet-stream")
        
        if file_size < threshold:
            # For files below threshold, encode inline as Base64.
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
            processed_parts.append(part)
        else:
            # For larger files, use the Gemini File API.
            try:
                file_ref = client.files.upload(file=file_path)
                processed_parts.append(file_ref)
            except Exception as e:
                raise RuntimeError(f"Error uploading file '{filename}': {e}")
    
    return processed_parts
