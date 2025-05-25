import os
import json # Import json
from PyQt6.QtWidgets import QWidget, QFormLayout, QTextEdit, QLabel
from core.env import ROOT_DIR  # Centralized root directory
from core import logging # Use Voidframe logger
from pathlib import Path # Use Path

class GlobalSettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Use Path objects and .json extension
        self.storage_dir = ROOT_DIR / "storage"
        self.system_prompt_path = self.storage_dir / "system_prompt.json"
        self.user_info_path = self.storage_dir / "user_info.json"

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        form_layout = QFormLayout()

        # System Prompt Field
        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setToolTip("Global instructions prepended to conversations for all APIs.")
        form_layout.addRow("Main System Prompt:", self.system_prompt_input)

        # User Info Field
        self.user_info_input = QTextEdit()
        self.user_info_input.setToolTip("Optional information about the user (currently not automatically used by core).")
        form_layout.addRow("User Info:", self.user_info_input)

        self.setLayout(form_layout)

    def load_settings(self):
        """Loads system prompt and user info from storage."""
        logging.logger.debug(f"Loading global settings from {self.system_prompt_path} and {self.user_info_path}")
        # Assume files contain plain text, even if named .json
        self.system_prompt_input.setPlainText(self._read_file(self.system_prompt_path))
        self.user_info_input.setPlainText(self._read_file(self.user_info_path))

    def save_settings(self):
        """Saves system prompt and user info back to their respective files."""
        logging.logger.debug(f"Saving global settings to {self.system_prompt_path} and {self.user_info_path}")
        system_prompt = self.system_prompt_input.toPlainText().strip()
        user_info = self.user_info_input.toPlainText().strip()

        # Save as plain text, even though filename is .json
        self._write_file(self.system_prompt_path, system_prompt)
        self._write_file(self.user_info_path, user_info)
        logging.logger.info("Global prompt settings saved.")

    def _read_file(self, file_path: Path):
        """Reads content from a file, returning an empty string if not found or error."""
        if file_path.exists():
            try:
                # Read as plain text
                return file_path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logging.logger.error(f"Error reading global settings file {file_path}: {e}")
        return ""

    def _write_file(self, file_path: Path, content: str):
        """Writes content to a file as plain text."""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            # Write as plain text
            file_path.write_text(content, encoding="utf-8")
        except Exception as e:
            logging.logger.error(f"Error writing global settings to {file_path}: {e}")