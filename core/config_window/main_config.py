import sys
from PyQt6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QLabel
from PyQt6.QtCore import Qt
# Import tab widgets
from core.config_window.models_config_tab import ModelsConfigWidget
from core.config_window.plugins_config_tab import PluginsConfigWidget
from core.config_window.global_config_tab import GlobalSettingsWidget
from core import logging # Use Voidframe logger

class ConfigWindow(QWidget):
    """Main configuration window holding different setting tabs."""

    def __init__(self, data_router, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.resize(800, 600) # Default size
        self.data_router = data_router
        # References to tab widgets
        self.models_tab: Optional[ModelsConfigWidget] = None
        self.plugins_tab: Optional[PluginsConfigWidget] = None
        self.global_tab: Optional[GlobalSettingsWidget] = None
        # Init UI elements
        self.summary_label: Optional[QLabel] = None
        self.tab_widget: Optional[QTabWidget] = None

        self.init_ui()
        # Update summary after UI initialization
        self.update_summary_field()

    def init_ui(self):
        """Sets up the UI layout and populates tabs."""
        main_layout = QVBoxLayout(self) # Set layout on this widget

        # Summary Label at the top
        self.summary_label = QLabel("Loading configuration summary...")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setWordWrap(True)
        main_layout.addWidget(self.summary_label)

        # Tab Widget for different settings categories
        self.tab_widget = QTabWidget()
        try:
            # Instantiate each tab, passing the DataRouter
            self.models_tab = ModelsConfigWidget(self.data_router, self) # Pass self as parent if needed
            self.plugins_tab = PluginsConfigWidget(self.data_router, self)
            self.global_tab = GlobalSettingsWidget(self)

            # Add tabs to the widget
            self.tab_widget.addTab(self.models_tab, "APIs & Models")
            self.tab_widget.addTab(self.plugins_tab, "Plugins")
            self.tab_widget.addTab(self.global_tab, "Global Prompts")
        except Exception as e:
             logging.logger.exception("Error initializing configuration tabs")
             # Display error within the window if tabs fail to load
             error_label = QLabel(f"FATAL ERROR loading configuration tabs:\n{e}\n\nPlease check logs.")
             error_label.setStyleSheet("color: red; font-weight: bold;")
             main_layout.addWidget(error_label)
             # Disable save? Or let partial save proceed?

        main_layout.addWidget(self.tab_widget)

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        button_layout.addStretch() # Push buttons to the right

        save_button = QPushButton("Save && Close")
        save_button.setToolTip("Save all changes and close the configuration window.")
        save_button.clicked.connect(self.save_settings)

        cancel_button = QPushButton("Cancel")
        cancel_button.setToolTip("Discard changes and close the window.")
        cancel_button.clicked.connect(self.close) # Simply closes the window

        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)

        # Optional: Connect tab change signal if needed elsewhere
        # self.tab_widget.currentChanged.connect(self.on_tab_changed)


    def update_summary_field(self):
        """Updates the summary label with current API/Model and plugins."""
        if not self.summary_label: return # Prevent error if called before init_ui finishes
        # *** Corrected try...except block ***
        try:
            active_api = self.data_router.active_api_name or "None"
            active_model = self.data_router.active_model_name or "None"
            api_model_text = f"Selected: {active_api} / {active_model}"
            plugins_text = "N/A"
            if self.data_router.plugin_manager:
                 loaded_plugins = self.data_router.plugin_manager.list_plugins()
                 plugins_text = f"Plugins: {', '.join(loaded_plugins) if loaded_plugins else 'None'}" # TODO: Show *enabled* plugins
            self.summary_label.setText(f"{api_model_text} | {plugins_text}")
        except Exception as e:
             logging.logger.error(f"Error updating config summary field: {e}", exc_info=True)
             self.summary_label.setText("Error loading summary.")


    def save_settings(self):
        """Saves Global settings and API parameters to the state file via DataRouter."""
        logging.logger.info("Attempting to save settings from ConfigWindow.")
        save_actions_successful = True
        error_messages = []

        # 1. Save Global Settings
        try:
            if self.global_tab: self.global_tab.save_settings()
            else: logging.logger.warning("Global settings tab unavailable.")
        except Exception as e: all_saves_successful=False; error_messages.append(f"Global: {e}"); logging.logger.exception("Err save global")

        # 2. Save API/Model Parameters for the *currently active* API
        try:
            if self.models_tab:
                 active_api = self.data_router.active_api_name
                 if active_api:
                     ui_param_values = self.models_tab.get_ui_parameter_values(active_api)
                     if ui_param_values is not None:
                          logging.logger.info(f"Requesting save for API '{active_api}' parameters: {ui_param_values}")
                          if not self.data_router.save_api_settings(active_api, ui_param_values):
                               save_actions_successful = False; error_messages.append(f"Failed to save parameters for '{active_api}'.")
                     else:
                          logging.logger.warning(f"Parameter validation failed for '{active_api}'. Not saving.")
                          save_actions_successful = False
                 else: logging.logger.warning("No active API; cannot save parameters.")
            else: logging.logger.warning("Models tab unavailable; cannot save parameters.")
        except Exception as e: all_saves_successful=False; error_messages.append(f"Params: {e}"); logging.logger.exception("Err save params")

        # 3. Save Plugin State (Deferred)
        # ... (unchanged placeholder) ...

        # Final Feedback
        if save_actions_successful:
            QMessageBox.information(self, "Settings Saved", "Configuration settings have been saved.")
            self.update_summary_field(); self.close()
        else:
             QMessageBox.warning(self, "Save Error", "Some settings could not be saved:\n\n" + "\n".join(error_messages)); self.update_summary_field()


# Test block unchanged
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import pyqtSignal # Need signal for dummy
    class DummyAPIInterface: # Simplified
        def list_available_apis(self): return ["DummyAPI"]
        def list_models(self, api): return ["ModelX"]
        def get_model_info(self, api, model): return "Info..."
        api_configs = {"DummyAPI": {"generation_parameters": {"temp": 0.5}, "alterable_settings": [{"name": "temp", "default": 0.5}]}}
    class DummyPluginManager:
        def list_plugins(self): return ["DummyPlugin"]
    class DummyDataRouter:
        # Add signal for compatibility with ModelsConfigWidget test
        parametersChanged = pyqtSignal()
        def __init__(self):
            self.api_interface = DummyAPIInterface()
            self.plugin_manager = DummyPluginManager()
            self.active_api_name = "DummyAPI"; self.active_model_name = "ModelX"
        # Simulate methods needed by config window
        def get_stored_api_settings(self, api_name): return {"selected_model": "ModelX", "temperature": 0.6} # Simulate
        def save_api_settings(self, api_name, settings_dict): print(f"Save {api_name}: {settings_dict}"); return True
        def set_user_selection(self, api, model): print(f"Set Sel {api}/{model}")
    app = QApplication(sys.argv)
    win = ConfigWindow(DummyDataRouter())
    win.show()
    sys.exit(app.exec())