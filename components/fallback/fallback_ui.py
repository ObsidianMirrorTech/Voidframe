import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QMessageBox, QSizePolicy # Changed imports
)
# Removed QMainWindow, QAction, QKeySequence
from PyQt6.QtCore import Qt
from core.ui_base import UIBase
from core import logging # Import logger

# --- Inherit QWidget, UIBase ---
class FallbackChatWindow(QWidget, UIBase):
    """
    A minimal fallback UI widget displayed when the configured UI plugin fails to load.
    It provides access to the configuration window via the main window's menu.
    """
    def __init__(self, error_message="Failed to load configured UI plugin."):
        super().__init__() # Initialize QWidget
        self.data_router = None
        # self.setWindowTitle("...") # REMOVED - Main window sets title
        # self.setGeometry(...) # REMOVED - Main window/layout controls size

        self.error_message = error_message
        self.info_label = QLabel() # Central label for messages
        self.init_ui()

    def init_ui(self):
        # Central Widget showing the error
        layout = QVBoxLayout(self) # Set layout directly on this QWidget

        # --- Menu Bar REMOVED ---
        # Configuration is accessed via the main window's File menu

        self.info_label.setText(f"<b>UI Load Failed:</b><br>{self.error_message}<br><br>Please use the main '<b>File > Configure...</b>' menu to select a valid UI plugin.")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setWordWrap(True)
        # Make label expand to fill space
        self.info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.info_label)
        self.setLayout(layout)

    # --- _open_configuration REMOVED (Handled by main window menu) ---

    # --- Implementation of UIBase abstract methods ---

    def get_widget(self) -> QWidget:
        """Returns the main QWidget of the UI (this widget itself)."""
        return self

    def set_data_router(self, data_router):
        """Sets the DataRouter instance."""
        self.data_router = data_router
        logging.logger.debug("DataRouter set for FallbackChatWindow")

    def handle_core_event(self, event_type: str, data: dict):
        """Handles events triggered by the core application."""
        logging.logger.debug(f"FallbackUI Received Event: {event_type}, Data: {data}") # Log all events

        if event_type == "new_message":
            # Fallback UI doesn't have a chat display, just log it
            role = data.get("role", "unknown")
            content = data.get("content", "")
            logging.logger.info(f"FallbackUI Display ({role}): {content}") # Log to console/file
        elif event_type == "display_cleared":
            logging.logger.info("FallbackUI: Display cleared.")
            # Reset the central label maybe?
            # self.info_label.setText("Display Cleared. Use File > Configure...")
        elif event_type == "show_message":
            # Handle requests to show modal messages using QMessageBox
            # Make sure the parent is correctly set if possible (using self should work)
            title = data.get("title", "Information")
            message = data.get("message", "")
            icon_str = data.get("icon", "information").lower()

            icon = QMessageBox.Icon.Information
            if icon_str == "warning": icon = QMessageBox.Icon.Warning
            elif icon_str == "critical": icon = QMessageBox.Icon.Critical
            elif icon_str == "question": icon = QMessageBox.Icon.Question
            # Use standard buttons like Ok
            QMessageBox(icon, title, message, QMessageBox.StandardButton.Ok, self).exec()
        else:
             logging.logger.warning(f"FallbackUI received unhandled event type: {event_type}")

    # --- show() method REMOVED (QWidget doesn't need explicit show like QMainWindow when embedded) ---

# Example of running just the fallback window for testing (optional)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Dummy DataRouter needed for set_data_router
    class DummyDataRouter:
         # Need dummy signals if UI were to connect back
         # But more importantly, need methods the UI might call if it had buttons
         # And need the attributes the UI might read
         active_api_name = "N/A"
         active_model_name = "N/A"
         plugin_manager = None
         api_interface = None
         # Dummy event handling methods if needed
         def handle_core_event(self, et, d): pass
         def show_config_window(self):
             QMessageBox.information(None, "Dummy Config", "Config window access via main File menu.")

    window = FallbackChatWindow("This is a test error message for standalone fallback.")
    dummy_router = DummyDataRouter()
    window.set_data_router(dummy_router) # Call set_data_router
    window.handle_core_event("show_message", {"title": "Test Popup", "message": "Testing show_message event.", "icon": "information"})
    window.show() # Need show() when running standalone
    sys.exit(app.exec())