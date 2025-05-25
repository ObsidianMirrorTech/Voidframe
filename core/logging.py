import os
import logging as py_logging
import sys # Import sys
from core.env import ROOT_DIR  # Import centralized root directory

LOG_DIR = ROOT_DIR / "storage" # Use Path object
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError as e:
     print(f"CRITICAL: Failed to create log directory {LOG_DIR}. Error: {e}")

LOG_FILE = LOG_DIR / "system.log" # Use Path object

# Updated logging format includes module name and line number for better traceability.
logging_format = "%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(message)s"
log_formatter = py_logging.Formatter(logging_format) # Create formatter once

# --- Configure Handlers ---
handlers = []

# File Handler (always try to add)
try:
    # Ensure log file path is a string for FileHandler
    file_handler = py_logging.FileHandler(str(LOG_FILE), encoding='utf-8') # Explicitly UTF-8 for file
    file_handler.setFormatter(log_formatter)
    handlers.append(file_handler)
except Exception as e:
    print(f"WARNING: Failed to create file handler for {LOG_FILE}. Error: {e}")

# Console (Stream) Handler - Simplified
try:
    # Use basic StreamHandler, let Python handle console encoding
    # This might still raise UnicodeEncodeError on some terminals for specific chars,
    # but should restore general logging to console.
    stream_handler = py_logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    handlers.append(stream_handler)
except Exception as e:
    print(f"WARNING: Failed to create stream handler. Console logging might be limited. Error: {e}")


# Basic Config (sets root logger level, attaches handlers)
# Using force=True to potentially override any default config
py_logging.basicConfig(
    level=py_logging.DEBUG,
    # format=logging_format, # Format is set on handlers now
    handlers=handlers,
    force=True
)

# Get specific logger instance AFTER basicConfig
logger = py_logging.getLogger("VoidframeLogger")
# Ensure this logger also processes DEBUG messages
logger.setLevel(py_logging.DEBUG)
# --- REMOVED logger.propagate = False --- to allow messages to reach root handlers

logger.debug("Logging system initialized with DEBUG level.")
# Test console encoding again (might fail on some consoles)
try:
    logger.debug("Testing Unicode: é Г 测试 👋")
    print("Console test: é Г 测试 👋")
except Exception as e: # Catch broader exception just in case
    logger.warning(f"Console logging test failed (may indicate encoding issues): {e}")