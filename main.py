import sys
import os
import json
import importlib.util
from pathlib import Path # Use Path
from PyQt6.QtWidgets import QApplication, QMessageBox, QMainWindow, QWidget
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtCore import pyqtSlot, QTimer
from typing import Optional

# --- Core Components ---
from core.data_router import DataRouter
from core.plugin_manager import PluginManager
from core.api_interface import APIInterface
# Use Any until ProjectManager defined
from typing import Any as ChatManager_or_ProjectManager
# from core.chat_manager import ChatManager # TODO: Replace with ProjectManager
from core.env import ROOT_DIR
from core.ui_base import UIBase
from core import logging

# --- Project Config Loading ---
def load_project_config():
    config_path = ROOT_DIR / "project_config.json" # Use Path
    try:
        with config_path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.logger.error(f"Project config file not found at {config_path}")
        QMessageBox.critical(None, "Startup Error", f"Project configuration file not found:\n{config_path}\n\nCannot start.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.logger.error(f"Error decoding project config file {config_path}: {e}")
        QMessageBox.critical(None, "Startup Error", f"Error reading project configuration file:\n{config_path}\n\nInvalid JSON: {e}\n\nCannot start.")
        sys.exit(1)
    except Exception as e:
        logging.logger.exception(f"Unexpected error loading project config {config_path}")
        QMessageBox.critical(None, "Startup Error", f"Unexpected error loading project configuration file:\n{config_path}\n\n{e}\n\nCannot start.")
        sys.exit(1)


# --- Main Window Class ---
class MainWindow(QMainWindow):
    def __init__(self, data_router: DataRouter, plugin_manager: PluginManager):
        super().__init__()
        self.data_router = data_router
        self.plugin_manager = plugin_manager
        self.current_ui_instance: Optional[UIBase] = None
        self.central_ui_widget: Optional[QWidget] = None

        self.setWindowTitle("Voidframe AI Interface")
        self.setGeometry(100, 100, 900, 700)

        self._create_menus()

        # Connect DataRouter Signals
        self.data_router.newMessageReady.connect(self._handle_new_message)
        self.data_router.apiErrorOccurred.connect(self._handle_api_error)
        self.data_router.showMessageRequest.connect(self._handle_show_message)
        self.data_router.clearDisplayRequest.connect(self._handle_clear_display)

        self._load_and_set_ui()

    def _create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        configure_action = QAction("&Configure...", self)
        configure_action.setShortcut(QKeySequence("Ctrl+O"))
        configure_action.triggered.connect(self.data_router.show_config_window)
        file_menu.addAction(configure_action)
        file_menu.addSeparator()
        exit_action = QAction("&Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _show_about_dialog(self):
        QMessageBox.about(self, "About Voidframe",
                          "Voidframe AI Interface\n\nA modular framework for AI interaction.")

    @pyqtSlot(dict)
    def _handle_new_message(self, message_data: dict):
        if self.current_ui_instance:
            try:
                self.current_ui_instance.handle_core_event("new_message", message_data)
            except Exception as e:
                logging.logger.exception(f"Error in UI instance ({type(self.current_ui_instance).__name__}) handling 'new_message' event")
                QMessageBox.critical(self, "UI Error", f"Error processing message in current UI:\n{e}")
        else:
            logging.logger.warning("Received newMessageReady signal, but no UI instance is active.")

    @pyqtSlot(str)
    def _handle_api_error(self, error_message: str):
        logging.logger.error(f"API Error received via signal: {error_message}")
        if self.current_ui_instance:
            try:
                self.current_ui_instance.handle_core_event("show_message", {
                    "title": "API Error", "message": error_message, "icon": "critical"
                })
            except Exception as e:
                logging.logger.exception(f"Error in UI instance ({type(self.current_ui_instance).__name__}) handling 'show_message' for API error")
                QMessageBox.critical(self, "API Error", error_message)
        else:
            logging.logger.warning("Received apiErrorOccurred signal, but no UI instance is active.")
            QMessageBox.critical(self, "API Error", error_message)

    @pyqtSlot(dict)
    def _handle_show_message(self, message_info: dict):
        if self.current_ui_instance:
            try:
                self.current_ui_instance.handle_core_event("show_message", message_info)
            except Exception as e:
                logging.logger.exception(f"Error in UI instance ({type(self.current_ui_instance).__name__}) handling 'show_message' event")
                title = message_info.get("title", "Information")
                message = message_info.get("message", "")
                QMessageBox.information(self, title, message)
        else:
            logging.logger.warning("Received showMessageRequest signal, but no UI instance is active.")
            title = message_info.get("title", "Information")
            message = message_info.get("message", "")
            QMessageBox.information(self, title, message)

    @pyqtSlot()
    def _handle_clear_display(self):
        if self.current_ui_instance:
             try:
                 self.current_ui_instance.handle_core_event("display_cleared", {})
             except Exception as e:
                 logging.logger.exception(f"Error in UI instance ({type(self.current_ui_instance).__name__}) handling 'display_cleared' event")
        else:
             logging.logger.warning("Received clearDisplayRequest signal, but no UI instance is active.")

    def _load_ui_plugin(self, ui_plugin_name: str) -> Optional[UIBase]:
        logging.logger.info(f"Attempting to load configured UI plugin: '{ui_plugin_name}' from interfaces")
        ui_instance = None
        error_msg = None
        try:
            plugin = self.plugin_manager.get_plugin(ui_plugin_name)
            if plugin and self.plugin_manager.get_plugin_type(ui_plugin_name) == 'interface':
                if hasattr(plugin, "get_ui"):
                    instance = plugin.get_ui()
                    if isinstance(instance, UIBase):
                        ui_instance = instance
                        logging.logger.info(f"Successfully retrieved UI instance from plugin: '{ui_plugin_name}'")
                    else:
                        error_msg = f"Plugin '{ui_plugin_name}' get_ui() method did not return a valid UIBase object (Type: {type(instance).__name__})."
                else:
                    error_msg = f"Interface Plugin '{ui_plugin_name}' was found but does not have a required get_ui() method."
            elif not plugin:
                 error_msg = f"UI Plugin '{ui_plugin_name}' was not found or failed to load. Check logs and plugin config."
            else:
                error_msg = f"Plugin '{ui_plugin_name}' found, but it's not an 'interface' type plugin."
        except Exception as e:
            logging.logger.exception(f"An unexpected error occurred while loading UI plugin '{ui_plugin_name}'")
            error_msg = f"Failed to load UI plugin '{ui_plugin_name}':\n{e}"

        if error_msg:
            logging.logger.error(error_msg)
            self.data_router.showMessageRequest.emit({"title":"UI Load Warning", "message":error_msg, "icon":"warning"})
            return None
        return ui_instance

    def _load_fallback_ui(self, reason: str) -> Optional[UIBase]:
        logging.logger.warning(f"Loading fallback UI due to error: {reason}")
        try:
            fallback_ui_path = ROOT_DIR / "components" / "fallback" / "fallback_ui.py"
            logging.logger.info(f"Attempting to load fallback UI from: {fallback_ui_path}")
            fallback_module_spec = importlib.util.spec_from_file_location("fallback_ui", str(fallback_ui_path)) # Needs str path
            if fallback_module_spec is None: raise ImportError(f"Spec not found at {fallback_ui_path}")
            fallback_module = importlib.util.module_from_spec(fallback_module_spec)
            fallback_module_spec.loader.exec_module(fallback_module)

            from components.fallback.fallback_ui import FallbackChatWindow
            fallback_instance = FallbackChatWindow(error_message=reason)

            if isinstance(fallback_instance, UIBase):
                logging.logger.info("Successfully loaded fallback UI instance.")
                return fallback_instance
            else:
                raise TypeError("Internal Fallback UI is invalid (does not implement UIBase).")
        except Exception as e:
            logging.logger.exception("Fatal error: Could not load internal fallback UI")
            self.data_router.showMessageRequest.emit({"title":"Fatal Error", "message":f"Could not load internal fallback UI:\n{e}\n\nExiting.", "icon":"critical"})
            QTimer.singleShot(100, QApplication.instance().quit)
            return None

    def _load_and_set_ui(self):
        project_config = load_project_config()
        selected_ui_name = project_config.get("selected_ui")
        loaded_ui: Optional[UIBase] = None

        if selected_ui_name:
            loaded_ui = self._load_ui_plugin(selected_ui_name)

        if loaded_ui is None:
            reason = f"Could not load configured UI '{selected_ui_name}'." if selected_ui_name else "No UI plugin specified in configuration."
            loaded_ui = self._load_fallback_ui(reason)

        if loaded_ui is None:
             logging.logger.critical("Failed to load both primary and fallback UI. Cannot continue.")
             return

        self.current_ui_instance = loaded_ui
        try:
             self.current_ui_instance.set_data_router(self.data_router)
             self.data_router.set_ui(self.current_ui_instance)

             ui_widget = self.current_ui_instance.get_widget()
             if not isinstance(ui_widget, QWidget):
                 raise TypeError(f"UI instance '{type(self.current_ui_instance).__name__}' get_widget() did not return a QWidget (returned {type(ui_widget).__name__}).")

             old_widget = self.centralWidget()
             if old_widget and old_widget != ui_widget:
                 old_widget.setParent(None)
                 old_widget.deleteLater()

             self.central_ui_widget = ui_widget
             self.setCentralWidget(self.central_ui_widget)
             logging.logger.info(f"Set central widget to: {type(self.central_ui_widget).__name__}")

             # TODO: Trigger plugin UI insertions (Phase 4)

        except Exception as e:
             logging.logger.exception("Error setting up loaded UI instance.")
             self.data_router.showMessageRequest.emit({"title":"Fatal Error", "message":f"Failed to set up loaded UI:\n{e}\n\nExiting.", "icon":"critical"})
             QTimer.singleShot(100, QApplication.instance().quit)


# --- Main execution block ---
def main():
    QApplication.setApplicationName("Voidframe")
    QApplication.setOrganizationName("VoidframeDev")
    app = QApplication(sys.argv)

    try:
        # Use Path object for consistency
        pre_storage_dir = ROOT_DIR / "storage"
        pre_storage_dir.mkdir(parents=True, exist_ok=True)
        logging.logger.info("--- Application Starting ---")
    except Exception as e:
         QMessageBox.critical(None, "Startup Error", f"Failed to create initial storage/log directory:\n{pre_storage_dir}\n\n{e}")
         sys.exit(1)

    try:
        # Load project config first
        project_config = load_project_config()

        # Determine storage dir using config
        storage_dir = ROOT_DIR / project_config.get("storage_directory", "storage")
        storage_dir.mkdir(parents=True, exist_ok=True)

        # Instantiate core components
        data_router = DataRouter()
        # Pass project_config to PluginManager
        plugin_manager = PluginManager(data_router, project_config)
        api_interface = APIInterface()

        # --- Dummy ChatManager (TEMPORARY) ---
        # TODO: Replace with ProjectManager in Phase 3
        class DummyChatManager:
             def __init__(self, storage_dir):
                 self.storage_dir = storage_dir
                 self.current_file="dummy_chat"
                 self.history = [] # Store history internally for get_chat_history
                 logging.logger.info("Initialized DummyChatManager")

             def append_message(self, msg_dict: dict): # Expects the dictionary
                 # *** Use logger instance ***
                 logging.logger.debug(f"DummyChatManager: Appending {msg_dict}")
                 self.history.append(msg_dict) # Add to internal history

             def get_chat_history(self) -> list:
                 logging.logger.debug("DummyChatManager: Getting history")
                 return list(self.history) # Return a copy

             def save_chat(self):
                 # In a real scenario, this would save self.history to a file
                 logging.logger.debug("DummyChatManager: Saving chat (no-op)")

             def create_new_chat(self):
                 logging.logger.debug("DummyChatManager: Creating new chat")
                 self.history = [] # Clear internal history
                 self.current_file = "new_dummy_chat"

             def load_most_recent_chat(self):
                 # In a real scenario, this would load from the latest file
                 logging.logger.debug("DummyChatManager: Loading most recent (no-op)")
                 self.history = [] # Start empty for dummy

        chat_manager = DummyChatManager(str(storage_dir)) # Pass str path if needed
        chat_manager.load_most_recent_chat() # Call initial load for dummy
        # --- End Dummy ChatManager ---

        # Register components AFTER they are all created
        data_router.register_components(api_interface, chat_manager, plugin_manager)

        # Plugin loading happens in PluginManager's __init__ now
        logging.logger.info("PluginManager initialized, plugins should be loaded.")

    except Exception as e:
        logging.logger.exception("Fatal error during core component initialization.")
        QMessageBox.critical(None, "Fatal Error", f"Core component initialization failed:\n{e}\n\nExiting.")
        sys.exit(1)

    # Create and show the main window
    try:
        main_window = MainWindow(data_router, plugin_manager)
        main_window.show()
        logging.logger.info("Application startup complete. Main window displayed.")

        # TODO: Trigger plugin on_load (Phase 4)

        sys.exit(app.exec())

    except Exception as e:
        logging.logger.exception("Unhandled exception during MainWindow creation or run.")
        QMessageBox.critical(None, "Fatal Error", f"An unexpected error occurred during application startup:\n{e}\n\nExiting.")
        sys.exit(1)

if __name__ == "__main__":
    main()