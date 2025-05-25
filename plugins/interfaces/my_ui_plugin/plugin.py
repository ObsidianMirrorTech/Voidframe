from core.ui_base import UIBase
# --- Add QHBoxLayout ---
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QMessageBox
from PyQt6.QtCore import Qt

class MyUI(QWidget, UIBase):
    def __init__(self, plugin_dir, config):
        super().__init__() # Initialize QWidget part
        self.plugin_dir = plugin_dir
        self.config = config
        self._data_router = None
        # UI elements
        self.label = QLabel("My Custom UI")
        self.input_field = QTextEdit()
        self.send_button = QPushButton("Send")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self) # Set layout on self
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1) # Add label to main layout

        # Input Area Layout
        input_layout = QHBoxLayout() # Now defined
        self.input_field.setFixedHeight(80)
        input_layout.addWidget(self.input_field)
        self.send_button.clicked.connect(self.handle_send_button)
        input_layout.addWidget(self.send_button)

        # Add input layout to main layout
        layout.addLayout(input_layout)
        # No need for self.setLayout(layout) as it was passed in constructor

    def handle_send_button(self):
        """Handle the send button click."""
        if self._data_router:
            user_input = self.input_field.toPlainText().strip()
            if user_input:
                self.input_field.clear()
                self._data_router.handle_user_input(user_input)

    # --- Implementation of UIBase abstract methods (remain the same) ---

    def get_widget(self) -> QWidget:
        return self

    def set_data_router(self, data_router):
        self._data_router = data_router

    def handle_core_event(self, event_type: str, data: dict):
        """Handles events from the core for this custom UI."""
        if event_type == "new_message":
            role = data.get("role", "unknown")
            content = data.get("content", "")
            safe_content = content.replace('<', '<').replace('>', '>') # Basic HTML safety
            # Append to the central label's existing text
            current_text = self.label.text()
            # Add line break if label isn't empty (avoid leading newline)
            separator = "\n" if current_text and not current_text.endswith('\n') else ""
            self.label.setText(current_text + f"{separator}{role.upper()}: {safe_content}")
        elif event_type == "display_cleared":
            self.label.setText("My Custom UI - Display Cleared")
        elif event_type == "show_message":
            title = data.get("title", "Info")
            message = data.get("message", "")
            icon_str = data.get("icon", "information").lower()
            icon = QMessageBox.Icon.Information
            if icon_str == "warning": icon = QMessageBox.Icon.Warning
            elif icon_str == "critical": icon = QMessageBox.Icon.Critical
            elif icon_str == "question": icon = QMessageBox.Icon.Question
            QMessageBox(icon, title, message, QMessageBox.StandardButton.Ok, self).exec()
        else:
             print(f"MyUI received unhandled event type: {event_type}")


# --- Required PluginBase wrapper (remains the same) ---
class PluginBase:
    def __init__(self, plugin_dir, config):
        self.plugin_dir = plugin_dir
        self.config = config
        # Instantiate the UI class defined above
        self.my_ui = MyUI(self.plugin_dir, self.config)

    def get_ui(self) -> UIBase:
        return self.my_ui