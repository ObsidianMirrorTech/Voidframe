from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QFormLayout, QLabel, QComboBox,
    QTextEdit, QPushButton, QLineEdit, QMessageBox, QDoubleSpinBox, QSpinBox,
    QApplication, QScrollArea, QHBoxLayout
)
from PyQt6.QtCore import Qt
from typing import Optional, Dict, Any, List, Tuple, Union
from core import logging
import math # For isnan

class ModelsConfigWidget(QWidget):
    """Tab widget for configuring API models and their parameters."""

    def __init__(self, data_router, parent=None):
        super().__init__(parent)
        self.data_router = data_router
        # UI Elements Storage
        self.settings_fields: Dict[str, Dict[str, QWidget]] = {} # Stores {api_name: {param_name: widget}}
        self.model_dropdowns: Dict[str, QComboBox] = {} # Stores {api_name: combobox_widget}
        self.settings_layouts: Dict[str, QFormLayout] = {} # Stores {api_name: form_layout}
        # Metadata Storage - Keep info about how to create/validate fields
        self.alterable_settings_info: Dict[str, Dict[str, Dict]] = {} # {api_name: {param_name: setting_info_dict}}
        # Flag to prevent race conditions during init/tab change
        self._loading_fields = False

        # Need api_tab_widget defined before connecting signals that might use it
        self.api_tab_widget = QTabWidget()

        self.init_ui() # Build UI elements

        # Connect signals AFTER init_ui might have added tabs
        self.api_tab_widget.currentChanged.connect(self.on_tab_changed)


    def init_ui(self):
        """Initializes the UI layout and widgets for the Models tab."""
        logging.logger.debug("ModelsConfigWidget init_ui started.")
        main_layout = QVBoxLayout(self)
        api_interface = self.data_router.api_interface
        apis = api_interface.list_available_apis() if api_interface else []

        if not apis:
            main_layout.addWidget(QLabel("No valid APIs discovered or loaded. Check logs and API configurations."))
            main_layout.addStretch() # Push label up
        else:
            is_first_tab = True # Track the first API added
            for api_name in apis:
                logging.logger.debug(f"ModelsConfigWidget init_ui: Creating tab for {api_name}")
                # --- Create Tab Structure ---
                api_tab = QWidget()
                tab_layout = QVBoxLayout(api_tab)

                # --- Model Selection Area ---
                model_form_layout = QFormLayout()
                model_dropdown = QComboBox()
                self.model_dropdowns[api_name] = model_dropdown # Store reference
                models = api_interface.list_models(api_name)
                model_dropdown.addItems(models if models else ["No models listed"])
                model_dropdown.setEnabled(bool(models))
                model_dropdown.currentTextChanged.connect(
                    lambda text, api=api_name: self._update_model_info(api, text)
                )
                model_form_layout.addRow("Select Model:", model_dropdown)

                description_widget = QTextEdit()
                description_widget.setObjectName(f"description_{api_name}") # Unique object name
                description_widget.setReadOnly(True); description_widget.setFixedHeight(60)
                description_widget.setToolTip("Information about the selected model (from API's info.json or config.json).")
                model_form_layout.addRow("Model Info:", description_widget)

                select_button = QPushButton("Set as Active API && Model")
                select_button.setToolTip(f"Make '{api_name}' with the selected model the active choice for new chats.\n(Saves immediately)")
                select_button.clicked.connect(lambda checked, name=api_name: self.on_select(name))
                model_form_layout.addRow("", select_button) # Add button without label

                tab_layout.addLayout(model_form_layout) # Add model selection to tab

                # --- Settings Area (Scrollable) ---
                settings_label = QLabel(f"Parameters for {api_name}:")
                settings_label.setStyleSheet("font-weight: bold;") # Make label stand out
                tab_layout.addWidget(settings_label)

                scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setMinimumHeight(200)
                settings_container_widget = QWidget()
                settings_form_layout = QFormLayout(settings_container_widget) # Create the layout
                # *** Store reference IMMEDIATELY ***
                self.settings_layouts[api_name] = settings_form_layout
                # *** ADDED DIAGNOSTIC LOG ***
                logging.logger.debug(f"ModelsConfigWidget init_ui: Stored layout for '{api_name}' (ID: {id(settings_form_layout)}). Current keys: {list(self.settings_layouts.keys())}")
                scroll_area.setWidget(settings_container_widget)
                tab_layout.addWidget(scroll_area)

                # --- Restore Defaults Button ---
                restore_defaults_button = QPushButton("Reset Parameters to API Defaults")
                restore_defaults_button.setToolTip("Reset parameter fields below to the defaults defined in the API's config.json.\n(Does not save automatically)")
                restore_defaults_button.clicked.connect(lambda checked, name=api_name: self.restore_defaults(name))
                button_hbox = QHBoxLayout(); button_hbox.addWidget(restore_defaults_button); button_hbox.addStretch()
                tab_layout.addLayout(button_hbox)

                self.api_tab_widget.addTab(api_tab, api_name)

                # *** Load fields for the FIRST tab immediately ***
                if is_first_tab:
                    logging.logger.debug(f"ModelsConfigWidget init_ui: Attempting immediate field load for first tab '{api_name}'")
                    self.load_api_settings_fields(api_name) # Load first tab immediately
                    is_first_tab = False

            main_layout.addWidget(self.api_tab_widget)
        logging.logger.debug("ModelsConfigWidget init_ui finished.")


    def on_tab_changed(self, index: int):
        """Loads settings fields when a tab becomes visible if not already loaded."""
        if self._loading_fields or index == -1: return
        api_name = self.api_tab_widget.tabText(index)
        logging.logger.debug(f"Tab changed to index {index}, API: '{api_name}'")

        if api_name and (api_name not in self.settings_fields or not self.settings_fields.get(api_name)):
             logging.logger.debug(f"Fields for '{api_name}' not yet loaded or empty. Proceeding to load.")
             if api_name in self.settings_layouts:
                  self.load_api_settings_fields(api_name)
             else:
                  logging.logger.error(f"Tab change Error: Layout for '{api_name}' not found. Keys: {list(self.settings_layouts.keys())}")
        elif api_name:
            logging.logger.debug(f"Fields for '{api_name}' already loaded/populated. Skipping load on tab change.")


    def _update_model_info(self, api_name, model_name):
        """Updates the description text area for the selected model."""
        tab_index = -1
        for i in range(self.api_tab_widget.count()):
             if self.api_tab_widget.tabText(i) == api_name: tab_index = i; break
        if tab_index == -1: return
        tab_widget = self.api_tab_widget.widget(tab_index)
        if not tab_widget: return
        description_widget = tab_widget.findChild(QTextEdit, f"description_{api_name}")
        if description_widget and self.data_router.api_interface:
             if model_name and model_name != "No models listed":
                 try:
                      desc_text = self.data_router.api_interface.get_model_info(api_name, model_name)
                      description_widget.setPlainText(str(desc_text))
                 except Exception as e:
                      logging.logger.error(f"Error getting model info for {api_name}/{model_name}: {e}")
                      description_widget.setPlainText(f"Error loading info for '{model_name}'.")
             else: description_widget.setPlainText("N/A - No model selected or available.")
        elif description_widget: description_widget.setPlainText("Error: API Interface not available.")


    def on_select(self, api_name):
        """Sets the selected API and Model as active via DataRouter."""
        if api_name not in self.model_dropdowns:
             logging.logger.error(f"Cannot set active API: Dropdown for '{api_name}' not found.")
             return
        combo = self.model_dropdowns[api_name]
        selected_model = combo.currentText()
        if not selected_model or selected_model == "No models listed":
             QMessageBox.warning(self, "No Model Selected", f"Please select a valid model for '{api_name}'.")
             return
        current_api = self.data_router.active_api_name
        current_model = self.data_router.active_model_name
        if current_api != api_name or current_model != selected_model:
             logging.logger.info(f"User selected new active API/Model: {api_name} / {selected_model}")
             try:
                 self.data_router.set_user_selection(api_name, selected_model)
                 QMessageBox.information(self, "Selection Applied", f"Set '{api_name} / {selected_model}' active.")
                 parent_window = self.window()
                 if parent_window and hasattr(parent_window, 'update_summary_field'):
                     parent_window.update_summary_field()
             except Exception as e:
                  logging.logger.exception(f"Error setting selection {api_name}/{selected_model}")
                  QMessageBox.critical(self, "Error Applying Selection", f"Failed: {e}")
        else:
             QMessageBox.information(self, "Selection Unchanged", f"'{api_name} / {selected_model}' is already active.")


    def load_api_settings_fields(self, api_name):
        """Creates and populates UI fields based on API config and saved state."""
        if self._loading_fields:
             logging.logger.warning(f"Re-entry prevented: load_api_settings_fields('{api_name}').")
             return
        self._loading_fields = True

        # *** ADDED DIAGNOSTIC LOGS ***
        logging.logger.debug(f"load_api_settings_fields: Attempting to get layout for '{api_name}'.")
        logging.logger.debug(f"load_api_settings_fields: Current self.settings_layouts keys: {list(self.settings_layouts.keys())}")
        logging.logger.debug(f"load_api_settings_fields: Full self.settings_layouts dict: {self.settings_layouts}") # Log the whole dict
        settings_layout = self.settings_layouts.get(api_name)
        logging.logger.debug(f"load_api_settings_fields: Result of get('{api_name}') is: {settings_layout} (Type: {type(settings_layout)}, ID: {id(settings_layout) if settings_layout else 'N/A'})")
        # *** END DIAGNOSTIC LOGS ***

        if not settings_layout:
             logging.logger.error(f"CRITICAL: Layout for API '{api_name}' could not be retrieved from self.settings_layouts during load.")
             self._loading_fields = False; return
        if not self.data_router or not self.data_router.api_interface:
             logging.logger.error("DataRouter or APIInterface missing in load_api_settings_fields.")
             self._loading_fields = False; return

        logging.logger.info(f"Starting field load process for API: {api_name}")

        # Clear existing fields
        self.settings_fields[api_name] = {}
        self.alterable_settings_info[api_name] = {}
        while settings_layout.rowCount() > 0:
             row_item = settings_layout.takeRow(0)
             if row_item.labelItem and row_item.labelItem.widget(): row_item.labelItem.widget().deleteLater()
             if row_item.fieldItem and row_item.fieldItem.widget(): row_item.fieldItem.widget().deleteLater()
        logging.logger.debug(f"Cleared existing fields for {api_name}.")

        # Get Config and State
        api_config = self.data_router.api_interface.api_configs.get(api_name, {})
        default_params_from_config = api_config.get("generation_parameters", {})
        alterable_settings_list = api_config.get("alterable_settings", [])
        logging.logger.debug(f"Retrieved alterable_settings for {api_name}: {alterable_settings_list}")
        saved_settings_values = self.data_router.get_stored_api_settings(api_name)
        saved_model_name = saved_settings_values.get("selected_model")

        # Set Model Dropdown and Info
        if api_name in self.model_dropdowns and saved_model_name:
             combo = self.model_dropdowns[api_name]
             index = combo.findText(saved_model_name, Qt.MatchFlag.MatchExactly)
             if index >= 0:
                  combo.blockSignals(True); combo.setCurrentIndex(index); combo.blockSignals(False)
                  logging.logger.debug(f"Set dropdown for '{api_name}' to saved: '{saved_model_name}'")
             else: logging.logger.warning(f"Saved model '{saved_model_name}' not in dropdown for '{api_name}'.")
        current_model_text = self.model_dropdowns.get(api_name).currentText() if api_name in self.model_dropdowns else "N/A"
        self._update_model_info(api_name, current_model_text)


        # Create Fields for Alterable Settings
        if not alterable_settings_list:
            logging.logger.info(f"No alterable settings defined for '{api_name}'. Adding info label.")
            settings_layout.addRow(QLabel("No configurable parameters defined for this API."))
            self._loading_fields = False; return

        logging.logger.debug(f"Starting loop to create {len(alterable_settings_list)} fields for {api_name}.")
        field_creation_success = True
        for index, setting_info in enumerate(alterable_settings_list):
            logging.logger.debug(f"  Processing setting index {index}: {setting_info}")
            if not isinstance(setting_info, dict) or "name" not in setting_info:
                logging.logger.warning(f"  Skipping invalid item: {setting_info}")
                continue

            param_name = setting_info["name"]
            label_text = setting_info.get("label", param_name)
            tooltip = setting_info.get("tooltip", f"Parameter: {param_name}")

            default_val_from_api_config = default_params_from_config.get(param_name)
            value_to_display = saved_settings_values.get(param_name, default_val_from_api_config)

            logging.logger.debug(f"    Param '{param_name}': Default='{default_val_from_api_config}', Saved='{saved_settings_values.get(param_name)}' -> Using '{value_to_display}'")

            self.alterable_settings_info[api_name][param_name] = setting_info
            field_widget: Optional[QWidget] = None
            label_widget = QLabel(label_text + ":"); label_widget.setToolTip(tooltip)

            # --- Widget Creation Logic ---
            try:
                target_py_type = type(default_val_from_api_config) if default_val_from_api_config is not None else str
                value_range: Optional[List[Union[int, float]]] = setting_info.get("range")
                step: Optional[Union[int, float]] = setting_info.get("step")
                is_int_type = target_py_type is int
                is_float_type = target_py_type is float

                if isinstance(value_range, list) and len(value_range) == 2 and (is_int_type or is_float_type):
                    try:
                        min_val, max_val = value_range
                        decimals = 2
                        if is_float_type:
                            try:
                                if step and float(step) > 0:
                                     step_float = float(step)
                                     if step_float != 0 and math.isfinite(step_float):
                                         step_str = format(step_float, '.10f').rstrip('0')
                                         if '.' in step_str: decimals = len(step_str.split('.')[-1])
                                min_float, max_float = float(min_val), float(max_val)
                                if math.isfinite(min_float):
                                     min_str = format(min_float, '.10f').rstrip('0')
                                     if '.' in min_str: decimals = max(decimals, len(min_str.split('.')[-1]))
                                if math.isfinite(max_float):
                                     max_str = format(max_float, '.10f').rstrip('0')
                                     if '.' in max_str: decimals = max(decimals, len(max_str.split('.')[-1]))
                            except Exception as dec_e: logging.logger.warning(f"Could not determine decimals for {param_name}: {dec_e}")

                        if is_float_type:
                            widget = QDoubleSpinBox()
                            widget.setDecimals(min(decimals, 10))
                            widget.setRange(float(min_val), float(max_val))
                            effective_step = 0.1**(min(decimals, 10))
                            try:
                                if step is not None: effective_step = float(step)
                            except (ValueError, TypeError): pass
                            widget.setSingleStep(effective_step)
                            try: widget.setValue(float(value_to_display) if value_to_display is not None else 0.0)
                            except (ValueError, TypeError): widget.setValue(float(default_val_from_api_config) if default_val_from_api_config is not None else 0.0); logging.logger.warning(f"Fallback value set for float {param_name}")
                            field_widget = widget

                        elif is_int_type:
                            widget = QSpinBox()
                            widget.setRange(int(min_val), int(max_val))
                            effective_step = 1
                            try:
                                if step is not None: effective_step = int(step)
                            except (ValueError, TypeError): pass
                            widget.setSingleStep(effective_step)
                            try: widget.setValue(int(value_to_display) if value_to_display is not None else 0)
                            except (ValueError, TypeError): widget.setValue(int(default_val_from_api_config) if default_val_from_api_config is not None else 0); logging.logger.warning(f"Fallback value set for int {param_name}")
                            field_widget = widget

                    except (ValueError, TypeError) as e:
                        logging.logger.warning(f"Error processing range/step for '{param_name}'. Falling back to QLineEdit. Error: {e}")
                        field_widget = None

                if field_widget is None:
                    widget = QLineEdit()
                    widget.setText(str(value_to_display if value_to_display is not None else default_val_from_api_config if default_val_from_api_config is not None else ""))
                    field_widget = widget

                field_widget.setToolTip(tooltip)
                settings_layout.addRow(label_widget, field_widget)
                self.settings_fields[api_name][param_name] = field_widget
                logging.logger.debug(f"    Successfully created widget for '{param_name}' (Type: {type(field_widget).__name__}) and added row.")

            except Exception as e:
                logging.logger.exception(f"    Error creating UI widget for parameter '{param_name}'.")
                settings_layout.addRow(label_widget, QLabel("<Error creating widget>"))
                field_creation_success = False

        if not field_creation_success:
             QMessageBox.warning(self, "Widget Creation Error", f"Errors occurred creating some parameter fields for '{api_name}'. Check logs.")

        logging.logger.info(f"Finished field load process for API: {api_name}.")
        self._loading_fields = False


    def refresh_parameter_fields_current_tab(self):
        """Refreshes fields for the currently visible tab by reloading them."""
        current_index = self.api_tab_widget.currentIndex()
        if current_index != -1:
            api_name = self.api_tab_widget.tabText(current_index)
            logging.logger.debug(f"Refreshing fields for current tab '{api_name}'.")
            self.load_api_settings_fields(api_name)


    def refresh_parameter_fields(self, api_name: Optional[str] = None):
        """Refreshes fields for a specific API tab (or current if None) by reloading."""
        target_api = api_name or self.get_selected_api()
        if target_api:
            logging.logger.debug(f"Refreshing fields for specific tab '{target_api}'.")
            self.load_api_settings_fields(target_api)


    def restore_defaults(self, api_name):
        """Resets UI fields for the given API to their default values from API config."""
        if api_name not in self.settings_fields or not self.settings_fields[api_name]:
            logging.logger.warning(f"Cannot restore defaults for '{api_name}': UI fields not loaded/created.")
            QMessageBox.information(self, "Cannot Restore", f"Parameter fields for '{api_name}' are not loaded.")
            return
        if not self.data_router.api_interface:
            logging.logger.error(f"Cannot restore defaults for '{api_name}': APIInterface missing.")
            return

        logging.logger.info(f"Restoring default parameter values in UI for API: {api_name}")
        restored_count = 0; error_count = 0
        api_config = self.data_router.api_interface.api_configs.get(api_name, {})
        default_params_from_config = api_config.get("generation_parameters", {})
        alterable_settings_list = api_config.get("alterable_settings", [])
        alterable_map = {s['name']: s for s in alterable_settings_list if isinstance(s, dict) and 'name' in s}

        for name, field_widget in self.settings_fields[api_name].items():
            default_val = alterable_map.get(name, {}).get('default')
            if default_val is None: default_val = default_params_from_config.get(name)

            if default_val is not None:
                try:
                    if isinstance(field_widget, QDoubleSpinBox): field_widget.setValue(float(default_val))
                    elif isinstance(field_widget, QSpinBox): field_widget.setValue(int(default_val))
                    elif isinstance(field_widget, QLineEdit): field_widget.setText(str(default_val))
                    else: logging.logger.warning(f"Unknown widget type '{type(field_widget)}' for '{name}'."); continue
                    restored_count += 1
                    logging.logger.debug(f"  Restored '{name}' to default: {default_val}")
                except (ValueError, TypeError) as e: logging.logger.error(f"Error converting/setting default '{default_val}' for '{name}': {e}"); error_count += 1
                except Exception as e: logging.logger.exception(f"Error restoring default for '{name}'"); error_count += 1
            else: logging.logger.debug(f"  No default value found for '{name}'.")

        if restored_count > 0 and error_count == 0: QMessageBox.information(self, "Defaults Restored", f"Restored {restored_count} fields for '{api_name}'.\nClick 'Save && Close' to apply.")
        elif restored_count > 0 and error_count > 0: QMessageBox.warning(self, "Partial Defaults Restored", f"Restored {restored_count} fields for '{api_name}'. Errors on {error_count} fields.\nClick 'Save && Close' to apply.")
        elif error_count > 0: QMessageBox.error(self, "Error Restoring Defaults", f"Errors on {error_count} fields for '{api_name}'.")
        else: QMessageBox.information(self, "No Defaults Found", f"No defaults found for '{api_name}'.")


    def get_selected_api(self) -> Optional[str]:
        """Returns the name of the API corresponding to the currently selected tab."""
        current_index = self.api_tab_widget.currentIndex()
        return self.api_tab_widget.tabText(current_index) if current_index != -1 else None


    def get_selected_model(self, api_name: Optional[str] = None) -> Optional[str]:
        """Gets the currently selected model name from the dropdown."""
        target_api = api_name or self.get_selected_api()
        if not target_api: return None
        combo = self.model_dropdowns.get(target_api)
        if combo:
            model_text = combo.currentText()
            if model_text and model_text != "No models listed": return model_text
        return None


    def get_ui_parameter_values(self, api_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Gets values from UI fields, validates, converts, and returns dict or None."""
        target_api = api_name or self.get_selected_api()
        if not target_api: logging.logger.error("Cannot get UI params: No target API."); return None

        if target_api not in self.settings_fields:
            api_config = self.data_router.api_interface.api_configs.get(target_api, {})
            if not api_config.get("alterable_settings"):
                 logging.logger.info(f"No UI fields defined for API '{target_api}'. Returning empty parameter dict.")
                 parameter_values = {}
                 selected_model = self.get_selected_model(target_api)
                 if selected_model: parameter_values["selected_model"] = selected_model
                 return parameter_values
            else:
                 logging.logger.warning(f"Settings fields dict entry missing for '{target_api}'. Load likely failed.")
                 return None

        api_fields = self.settings_fields[target_api]
        if not api_fields: # Check if the dict exists but is empty
            logging.logger.info(f"No UI parameter fields were created for API '{target_api}'. Returning only selected model.")
            parameter_values = {}
            selected_model = self.get_selected_model(target_api)
            if selected_model: parameter_values["selected_model"] = selected_model
            return parameter_values

        logging.logger.debug(f"Getting UI parameter values for API: {target_api}")
        parameter_values = {}
        validation_failed = False
        error_messages = []
        api_metadata = self.alterable_settings_info.get(target_api, {})
        api_config = self.data_router.api_interface.api_configs.get(target_api, {})
        api_config_defaults = api_config.get("generation_parameters", {})

        for param_name, widget in api_fields.items():
            setting_info = api_metadata.get(param_name)
            default_val_config = api_config_defaults.get(param_name)
            default_val_alt = setting_info.get('default') if setting_info else None
            if default_val_alt is not None: default_val_type = type(default_val_alt)
            elif default_val_config is not None: default_val_type = type(default_val_config)
            else: default_val_type = str

            raw_value: Union[str, int, float, None] = None
            try:
                if isinstance(widget, QLineEdit): raw_value = widget.text()
                elif isinstance(widget, QSpinBox): raw_value = widget.value()
                elif isinstance(widget, QDoubleSpinBox): raw_value = widget.value()
                else: logging.logger.warning(f"Unknown widget type '{type(widget)}' for '{param_name}'."); continue
            except Exception as e: logging.logger.error(f"Error reading widget for '{param_name}': {e}"); error_messages.append(f"Error reading '{param_name}'."); validation_failed = True; continue

            converted_value: Any = None
            try:
                if isinstance(raw_value, str) and not raw_value and default_val_type not in [str, type(None)]:
                     if default_val_type is bool: converted_value = False
                     else: raise ValueError("Empty value not allowed")
                elif default_val_type is float:
                    converted_value = float(raw_value)
                    if setting_info and 'range' in setting_info and isinstance(setting_info['range'], list) and len(setting_info['range']) == 2:
                         min_val, max_val = float(setting_info['range'][0]), float(setting_info['range'][1])
                         if not (min_val <= converted_value <= max_val): raise ValueError(f"Out of range [{min_val}, {max_val}]")
                elif default_val_type is int:
                    converted_value = int(raw_value)
                    if setting_info and 'range' in setting_info and isinstance(setting_info['range'], list) and len(setting_info['range']) == 2:
                         min_val, max_val = int(setting_info['range'][0]), int(setting_info['range'][1])
                         if not (min_val <= converted_value <= max_val): raise ValueError(f"Out of range [{min_val}, {max_val}]")
                elif default_val_type is bool:
                     if isinstance(raw_value, str):
                          if raw_value.lower() in ('true', '1', 'yes', 'y'): converted_value = True
                          elif raw_value.lower() in ('false', '0', 'no', 'n', ''): converted_value = False
                          else: raise ValueError("Invalid string for boolean")
                     else: converted_value = bool(raw_value)
                else: converted_value = str(raw_value)
                if default_val_type is float and math.isnan(converted_value): raise ValueError("Value is NaN")

                parameter_values[param_name] = converted_value
                logging.logger.debug(f"  Got value for '{param_name}': {converted_value} (Type: {type(converted_value).__name__})")
            except (ValueError, TypeError) as e:
                logging.logger.warning(f"Validation failed for '{param_name}' ('{raw_value}'): {e}")
                error_messages.append(f"Invalid '{setting_info.get('label', param_name)}': {e}")
                validation_failed = True

        if validation_failed:
            QMessageBox.warning(self, "Validation Error", "Invalid values:\n\n- " + "\n- ".join(error_messages))
            return None
        else:
            logging.logger.info(f"Successfully retrieved UI parameters for '{target_api}'.")
            selected_model = self.get_selected_model(target_api)
            if selected_model: parameter_values["selected_model"] = selected_model
            return parameter_values