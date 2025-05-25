from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget, QPushButton, # Removed QMenuBar
    QHBoxLayout, QSplitter, QSizePolicy, QMessageBox, QLabel
)
# Removed: from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import Qt, QTimer
from core.ui_base import UIBase

# --- Inherit QWidget, UIBase ---
class DefaultChatUI(QWidget, UIBase): # Changed from QMainWindow
    def __init__(self):
        super().__init__() # Initialize QWidget
        self.data_router = None
        self.chat_display = QTextEdit()
        self.input_field = QTextEdit()
        self.send_button = QPushButton("Send")
        # This layout will be set on the QWidget itself
        self.main_layout = QVBoxLayout(self) # Pass self to set layout on this widget
        self.init_ui()

    def init_ui(self):
        # self.setWindowTitle("...") # REMOVED - Main window sets title
        # --- Menu Bar REMOVED ---

        # Chat display area
        self.chat_display.setReadOnly(True)
        self.chat_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Input field area
        self.input_field.setFixedHeight(100)
        self.input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Send button
        self.send_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.send_button.clicked.connect(self.handle_input_button)

        # Input layout
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)

        # Main layout - Add widgets directly to self.main_layout
        self.main_layout.addWidget(self.chat_display)
        self.main_layout.addLayout(input_layout)

        # No setCentralWidget() needed - the layout is set on self

        # self.resize(800, 600) # REMOVED - Main window controls size

    # --- _open_configuration REMOVED (Handled by main window menu) ---

    def handle_input_button(self):
        """Handles the send button click."""
        if self.data_router:
            user_input = self.input_field.toPlainText().strip()
            if user_input:
                self.input_field.clear()
                self.data_router.handle_user_input(user_input)
        else:
            self._show_internal_message("Error: DataRouter not connected.", "Error", QMessageBox.Icon.Warning)

    # --- Implementation of UIBase abstract methods ---
    def get_widget(self) -> QWidget:
        # Return this widget itself
        return self

    def set_data_router(self, data_router):
        self.data_router = data_router

    def handle_core_event(self, event_type: str, data: dict):
        """Handles events from the core, updating the UI accordingly."""
        # (Implementation remains the same as before)
        if event_type == "new_message":
            role = data.get("role", "unknown")
            content = data.get("content", "")
            self._display_formatted_message(content, role)
        elif event_type == "display_cleared":
            self.chat_display.clear()
        elif event_type == "show_message":
            title = data.get("title", "Information")
            message = data.get("message", "")
            icon_str = data.get("icon", "information").lower()
            icon = QMessageBox.Icon.Information
            if icon_str == "warning": icon = QMessageBox.Icon.Warning
            if icon_str == "critical": icon = QMessageBox.Icon.Critical
            if icon_str == "question": icon = QMessageBox.Icon.Question
            if icon_str == "system": icon = QMessageBox.Icon.Information
            self._show_internal_message(message, title, icon)
        else:
             print(f"DefaultChatUI received unhandled event: {event_type}")

    # --- Internal Helper Methods ---
    # (Implementations remain the same as before)
    def _display_formatted_message(self, message: str, role: str):
        formatted_message = ""
        safe_message = message.replace('<', '<').replace('>', '>')
        if role == "user": formatted_message = f"<p style='color: blue;'><b>You:</b> {safe_message}</p>"
        elif role == "assistant": formatted_message = f"<p style='color: green;'><b>Assistant:</b> {safe_message}</p>"
        elif role == "system": formatted_message = f"<p style='color: gray;'><i>System: {safe_message}</i></p>"
        else: formatted_message = f"<p>{safe_message}</p>"
        self.chat_display.append(formatted_message)

    def _show_internal_message(self, message_text, title="Information", icon=QMessageBox.Icon.Information):
        # Parent should ideally be the main window, but 'self' might work for modality
        msg_box = QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setText(message_text)
        msg_box.setWindowTitle(title)
        msg_box.exec()

    # --- show() method REMOVED (Main window handles showing) ---

# --- Required PluginBase wrapper ---
# (Remains the same)
class PluginBase:
    def __init__(self, plugin_dir, config):
        self.plugin_dir = plugin_dir
        self.config = config
        self.ui_instance = DefaultChatUI() # Creates the QWidget

    def get_ui(self) -> UIBase: # Returns the instance which IS-A UIBase
        return self.ui_instance