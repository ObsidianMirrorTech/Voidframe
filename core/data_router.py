import threading
import time
import os
import json
from typing import TYPE_CHECKING, Optional, List, Dict, Any
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, pyqtSlot
from core import logging # Import the logging module setup
from core.env import ROOT_DIR

STATE_FILE_PATH = ROOT_DIR / "storage" / "program_state.json"

# Attempt to import ConfigWindow safely
try:
    from core.config_window.main_config import ConfigWindow
except ImportError:
    logging.logger.warning("Could not import ConfigWindow. Configuration window functionality will be unavailable.")
    ConfigWindow = None

if TYPE_CHECKING:
    from core.api_interface import APIInterface
    from typing import Any as ChatManager_or_ProjectManager
    from core.plugin_manager import PluginManager
    from core.ui_base import UIBase
    from PyQt6.QtWidgets import QWidget

# --- API Worker Thread ---
# [ApiWorker class remains the same as the previous version]
class ApiWorker(QRunnable):
    """
    Worker thread for executing API calls asynchronously.
    Emits signals on completion or error.
    """
    def __init__(self, data_router: 'DataRouter', api_name: str, request_data: dict):
        super().__init__()
        self.data_router = data_router # Store reference to DataRouter
        self.api_name = api_name
        self.request_data = request_data

    @pyqtSlot()
    def run(self):
        """Execute the API call."""
        try:
            if not self.data_router.api_interface:
                 logging.logger.error("APIInterface not available in DataRouter for worker.")
                 raise RuntimeError("APIInterface not available in DataRouter for worker.")

            logging.logger.info(f"API Worker started for API: '{self.api_name}'")
            start_time = time.monotonic()
            # Call the APIInterface's run_inference method
            response_text = self.data_router.api_interface.run_inference(
                self.api_name, self.request_data
            )
            end_time = time.monotonic()
            logging.logger.info(f"API Worker finished for '{self.api_name}'. Duration: {end_time - start_time:.2f}s")

            # --- Post-API Hooks ---
            modified_response = self.data_router._apply_post_api_hooks(response_text, self.request_data)
            if modified_response is None: # Hook indicated stop
                 logging.logger.warning("API call aborted after post_api hooks.")
                 return

            # --- Process successful response ---
            assistant_message = {"role": "assistant", "content": modified_response}

            # Append to history (via ChatManager/ProjectManager)
            if self.data_router.chat_manager:
                 try:
                      self.data_router.chat_manager.append_message(assistant_message)
                      logging.logger.debug("Assistant message appended to history.")
                 except AttributeError:
                      logging.logger.error("Chat manager missing 'append_message' method taking a dictionary.")
                 except Exception as e:
                      logging.logger.exception("Error appending assistant message to chat history.")
            else:
                 logging.logger.error("Chat Manager not available, cannot save assistant response.")


            # Emit signal for UI update (send the dict)
            self.data_router.newMessageReady.emit(assistant_message)
            logging.logger.debug("newMessageReady signal emitted for UI.")

            # --- Post-History Hooks ---
            current_history = self.data_router.chat_manager.get_chat_history() if self.data_router.chat_manager else []
            final_history = self.data_router._apply_post_history_hooks(current_history)
            if final_history is None:
                 logging.logger.warning("Processing stopped after post_history hooks.")
                 return

        except Exception as e:
            logging.logger.exception(f"Error in API worker thread for API '{self.api_name}'")
            error_message = f"API call to '{self.api_name}' failed:\n{type(e).__name__}: {e}"
            self.data_router.apiErrorOccurred.emit(error_message)

# --- Data Router Class ---
class DataRouter(QObject):
    newMessageReady = pyqtSignal(dict)
    apiErrorOccurred = pyqtSignal(str)
    showMessageRequest = pyqtSignal(dict)
    clearDisplayRequest = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.api_interface: Optional["APIInterface"] = None
        self.chat_manager: Optional["ChatManager_or_ProjectManager"] = None
        self.plugin_manager: Optional["PluginManager"] = None
        self.ui: Optional["UIBase"] = None
        self.config_window: Optional["ConfigWindow"] = None

        self.active_api_name: Optional[str] = None
        self.active_model_name: Optional[str] = None

        self._load_minimal_program_state()

        self.threadpool = QThreadPool()
        logging.logger.info(f"QThreadPool initialized. Max threads: {self.threadpool.maxThreadCount()}")


    def _read_state_file(self) -> dict:
        # [ Remains the same ]
        state_data = {}
        try:
            if STATE_FILE_PATH.exists():
                STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with STATE_FILE_PATH.open('r', encoding='utf-8') as f:
                    state_data = json.load(f)
            else:
                logging.logger.info(f"State file {STATE_FILE_PATH} not found. Returning empty state.")
        except (json.JSONDecodeError, IOError, Exception) as e:
            logging.logger.error(f"Error reading state file {STATE_FILE_PATH}: {e}", exc_info=True)
        return state_data

    def _write_state_file(self, state_data: dict) -> bool:
        # [ Remains the same ]
        logging.logger.debug(f"Attempting to write program state to {STATE_FILE_PATH}.")
        temp_file_path = STATE_FILE_PATH.with_suffix(".json.tmp")
        try:
            STATE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with temp_file_path.open('w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2)
            os.replace(temp_file_path, STATE_FILE_PATH)
            logging.logger.info(f"Program state saved successfully to {STATE_FILE_PATH}.")
            return True
        except (IOError, OSError, TypeError, Exception) as e:
            logging.logger.error(f"Error writing program state to {STATE_FILE_PATH}: {e}", exc_info=True)
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink(missing_ok=True)
                    logging.logger.debug(f"Removed temporary state file {temp_file_path} after write error.")
                except OSError as unlink_e:
                    logging.logger.error(f"Error removing temporary state file {temp_file_path}: {unlink_e}")
            self.showMessageRequest.emit({"title": "Save Error", "message": f"Could not save program state:\n{e}", "icon": "warning"})
            return False

    def _load_minimal_program_state(self):
        # [ Remains the same ]
        state_data = self._read_state_file()
        self.active_api_name = state_data.get("active_api")
        self.active_model_name = state_data.get("active_model")
        logging.logger.info(f"Loaded initial state: Active API='{self.active_api_name}', Active Model='{self.active_model_name}'")

    def _sync_and_default_all_api_settings(self):
        # [ Remains the same ]
        if not self.api_interface:
             logging.logger.error("Cannot sync API settings: APIInterface not available.")
             return False

        logging.logger.debug("Syncing API settings in program state...")
        state_data = self._read_state_file()
        if "api_settings" not in state_data or not isinstance(state_data.get("api_settings"), dict):
            logging.logger.warning("Initializing 'api_settings' dictionary in program state.")
            state_data["api_settings"] = {}
            needs_save = True
        else:
            needs_save = False

        stored_settings = state_data["api_settings"]
        available_apis = self.api_interface.list_available_apis()
        api_configs = self.api_interface.api_configs

        for api_name in available_apis:
            if api_name not in api_configs:
                logging.logger.warning(f"Skipping sync for API '{api_name}': Config not loaded in APIInterface.")
                continue

            api_defaults = api_configs[api_name].get("generation_parameters", {})
            default_model_for_api = api_configs[api_name].get("default_model")
            if not default_model_for_api:
                 models = self.api_interface.list_models(api_name)
                 if models: default_model_for_api = models[0]
            if not default_model_for_api:
                 logging.logger.warning(f"Could not determine a default model for API '{api_name}' from its config.")

            if api_name not in stored_settings:
                logging.logger.info(f"Adding default settings block for new API '{api_name}' to state.")
                new_block = api_defaults.copy()
                new_block["selected_model"] = default_model_for_api
                stored_settings[api_name] = new_block
                needs_save = True
            else:
                current_api_stored_settings = stored_settings[api_name]
                if not isinstance(current_api_stored_settings, dict):
                     logging.logger.warning(f"State data for API '{api_name}' is not a dict. Resetting to defaults.")
                     current_api_stored_settings = api_defaults.copy()
                     current_api_stored_settings["selected_model"] = default_model_for_api
                     stored_settings[api_name] = current_api_stored_settings
                     needs_save = True
                     continue

                for param_name, default_value in api_defaults.items():
                    if param_name not in current_api_stored_settings:
                        logging.logger.info(f"Adding missing param '{param_name}' default '{default_value}' for API '{api_name}'.")
                        current_api_stored_settings[param_name] = default_value
                        needs_save = True

                if "selected_model" not in current_api_stored_settings:
                     logging.logger.info(f"Adding missing 'selected_model' (using default '{default_model_for_api}') for API '{api_name}'.")
                     current_api_stored_settings["selected_model"] = default_model_for_api
                     needs_save = True

        apis_to_remove = [api for api in stored_settings if api not in available_apis]
        for api in apis_to_remove:
            logging.logger.info(f"Removing settings for obsolete API '{api}' from state.")
            del stored_settings[api]
            needs_save = True

        if self.active_api_name is None or self.active_api_name not in available_apis:
             if available_apis:
                  self.active_api_name = available_apis[0]
                  state_data["active_api"] = self.active_api_name
                  logging.logger.info(f"Setting default active API to '{self.active_api_name}'.")
                  needs_save = True
             else:
                  logging.logger.warning("No APIs available, cannot set a default active API.")
                  self.active_api_name = None
                  if "active_api" in state_data: del state_data["active_api"]
                  needs_save = True

        if self.active_api_name and (self.active_model_name is None or self.active_model_name not in self.api_interface.list_models(self.active_api_name)):
             default_model_for_current_api = stored_settings.get(self.active_api_name, {}).get("selected_model")
             if default_model_for_current_api:
                  self.active_model_name = default_model_for_current_api
                  state_data["active_model"] = self.active_model_name
                  logging.logger.info(f"Setting default active model to '{self.active_model_name}' (based on selected model for API '{self.active_api_name}').")
                  needs_save = True
             else:
                  models_for_active_api = self.api_interface.list_models(self.active_api_name)
                  if models_for_active_api:
                       self.active_model_name = models_for_active_api[0]
                       state_data["active_model"] = self.active_model_name
                       logging.logger.info(f"Setting default active model to first available for '{self.active_api_name}': '{self.active_model_name}'.")
                       needs_save = True
                  else:
                       logging.logger.warning(f"No models available for active API '{self.active_api_name}', cannot set a default active model.")
                       self.active_model_name = None
                       if "active_model" in state_data: del state_data["active_model"]
                       needs_save = True

        if needs_save:
            logging.logger.info("Saving synchronized API settings structure and default active API/Model.")
            self._write_state_file(state_data)

        return True

    def get_stored_api_settings(self, api_name: str) -> dict:
        # [ Remains the same ]
        state_data = self._read_state_file()
        return state_data.get("api_settings", {}).get(api_name, {}).copy()

    def save_api_settings(self, api_name: str, settings_dict: dict) -> bool:
        # [ Remains the same ]
        if not api_name:
             logging.logger.error("save_api_settings called with empty api_name.")
             return False
        state_data = self._read_state_file()

        if "api_settings" not in state_data or not isinstance(state_data.get("api_settings"), dict):
             state_data["api_settings"] = {}
        if api_name not in state_data["api_settings"] or not isinstance(state_data["api_settings"].get(api_name), dict):
             state_data["api_settings"][api_name] = {}

        if "selected_model" not in settings_dict and "selected_model" in state_data["api_settings"][api_name]:
             settings_dict["selected_model"] = state_data["api_settings"][api_name]["selected_model"]
             logging.logger.debug(f"Preserving existing 'selected_model' ('{settings_dict['selected_model']}') for API '{api_name}' during save.")

        state_data["api_settings"][api_name].update(settings_dict)
        logging.logger.info(f"Updating settings for API '{api_name}' in state file.")
        return self._write_state_file(state_data)

    def register_components(self, api_interface, chat_manager, plugin_manager):
        # [ Remains the same ]
        self.api_interface = api_interface
        self.chat_manager = chat_manager
        self.plugin_manager = plugin_manager
        logging.logger.info("Core components registered with DataRouter.")
        if not self._sync_and_default_all_api_settings():
             logging.logger.error("Initial API settings sync failed. State file might be inconsistent.")
             self.showMessageRequest.emit({
                 "title": "State Warning",
                 "message": "Failed to synchronize API settings in the program state file.\nSome settings might be missing or incorrect.",
                 "icon": "warning"
             })

    def set_ui(self, ui: "UIBase"):
        # [ Remains the same ]
        self.ui = ui
        logging.logger.info(f"Active UI instance set in DataRouter: {type(ui).__name__}")

    def show_config_window(self):
        # [ Remains the same ]
        logging.logger.debug("show_config_window called.")
        if ConfigWindow is None:
             logging.logger.error("Cannot open config window: ConfigWindow class failed to import.")
             self.showMessageRequest.emit({"title":"Error", "message":"Configuration window component failed to load.", "icon":"critical"})
             return

        if self.config_window is None or not self.config_window.isVisible():
             try:
                  logging.logger.info("Creating and showing configuration window.")
                  self.config_window = ConfigWindow(self)
                  self.config_window.show()
             except Exception as e:
                  logging.logger.exception("Failed to create or show ConfigWindow")
                  self.showMessageRequest.emit({"title":"Error", "message":f"Could not open configuration window:\n{e}", "icon":"critical"})
                  self.config_window = None
        else:
             logging.logger.info("Configuration window already open, activating.")
             self.config_window.activateWindow()
             self.config_window.raise_()

    def handle_user_input(self, user_input: str):
        # [ Remains the same ]
        logging.logger.info(f"Handling user input: '{user_input[:100]}...'")
        if not self.api_interface:
             logging.logger.error("Cannot handle input: APIInterface is not registered.")
             self.apiErrorOccurred.emit("Error: API Interface not configured.")
             return
        if not self.chat_manager:
             logging.logger.error("Cannot handle input: ChatManager/ProjectManager is not registered.")
             self.apiErrorOccurred.emit("Error: Chat/Project Manager not configured.")
             return
        if not self.plugin_manager:
             logging.logger.warning("PluginManager not registered. Proceeding without plugin hooks.")

        if not self.active_api_name:
             logging.logger.error("Cannot handle input: No active API selected.")
             self.apiErrorOccurred.emit("Error: No API is currently selected. Please configure an API.")
             return
        if not self.active_model_name:
             logging.logger.error("Cannot handle input: No active model selected for the current API.")
             self.apiErrorOccurred.emit(f"Error: No model selected for '{self.active_api_name}'. Please select a model in configuration.")
             return

        logging.logger.debug("Applying pre_history hooks...")
        modified_input = self._apply_pre_history_hooks(user_input)
        if modified_input is None:
             logging.logger.info("Input processing stopped by pre_history hook.")
             return
        user_input = modified_input

        user_message = {"role": "user", "content": user_input}
        try:
             self.chat_manager.append_message(user_message)
             logging.logger.debug("User message appended to history.")
             self.newMessageReady.emit(user_message)
             logging.logger.debug("newMessageReady signal emitted for user message.")
        except AttributeError:
             logging.logger.error("Chat manager missing 'append_message' method taking a dictionary.")
        except Exception as e:
             logging.logger.exception("Error appending user message to chat history.")
             self.apiErrorOccurred.emit(f"Error saving message to history: {e}")
             return

        try:
             current_chat_history = self.chat_manager.get_chat_history()
             logging.logger.debug(f"Retrieved chat history (length: {len(current_chat_history)}).")
        except AttributeError:
             logging.logger.error("Chat manager missing 'get_chat_history' method.")
             self.apiErrorOccurred.emit("Error retrieving chat history.")
             return
        except Exception as e:
             logging.logger.exception("Error getting chat history.")
             self.apiErrorOccurred.emit(f"Error retrieving chat history: {e}")
             return

        logging.logger.debug("Building API request data...")
        try:
             request_data = self.build_api_request_data(current_chat_history)
             logging.logger.debug(f"Built request data for API '{self.active_api_name}', Model '{self.active_model_name}'.")
        except Exception as e:
             logging.logger.exception("Error building API request data.")
             self.apiErrorOccurred.emit(f"Error preparing request: {e}")
             return

        logging.logger.debug("Applying pre_api hooks...")
        modified_request_data = self._apply_pre_api_hooks(request_data)
        if modified_request_data is None:
             logging.logger.info("API call stopped by pre_api hook.")
             return
        request_data = modified_request_data

        logging.logger.info(f"Dispatching API call to worker thread for API: '{self.active_api_name}'...")
        worker = ApiWorker(self, self.active_api_name, request_data)
        self.threadpool.start(worker)
        logging.logger.debug("API worker started in thread pool.")


    # --- Prompt Loading Helpers ---
    def _load_system_prompt(self) -> str:
        """Loads the global system prompt from storage (expects plain text in .json file)."""
        # *** Reverted to use .json extension ***
        prompt_path = ROOT_DIR / "storage" / "system_prompt.json"
        content = ""
        if prompt_path.exists():
            try:
                # Read as plain text, despite .json extension
                content = prompt_path.read_text(encoding='utf-8').strip()
                logging.logger.debug("Loaded system prompt from system_prompt.json")
            except Exception as e:
                logging.logger.error(f"Error reading system prompt file {prompt_path}: {e}")
        else:
             logging.logger.debug(f"System prompt file not found at {prompt_path}.")
        return content

    def _load_user_info(self) -> str:
        """Loads the global user info prompt from storage (expects plain text in .json file)."""
        # *** Reverted to use .json extension ***
        info_path = ROOT_DIR / "storage" / "user_info.json"
        content = ""
        if info_path.exists():
            try:
                 # Read as plain text, despite .json extension
                content = info_path.read_text(encoding='utf-8').strip()
                logging.logger.debug("Loaded user info from user_info.json")
            except Exception as e:
                logging.logger.error(f"Error reading user info file {info_path}: {e}")
        else:
             logging.logger.debug(f"User info file not found at {info_path}.")
        return content

    def build_api_request_data(self, current_chat_history: List[Dict]) -> Dict:
        # [ Minor logging changes from previous version, core logic same ]
        messages = []
        system_prompt = self._load_system_prompt()
        user_info = self._load_user_info()

        if system_prompt:
             messages.append({"role": "system", "content": system_prompt.strip()})
             logging.logger.debug("Prepended system prompt to messages.")
        if user_info:
             logging.logger.debug("User info loaded, but not automatically prepended to messages in this version.")

        for msg in current_chat_history:
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                 logging.logger.warning(f"Skipping invalid message format in history: {msg}")
                 continue
            msg_copy = msg.copy()
            msg_copy.setdefault("files", None)
            messages.append(msg_copy)

        project_id = None
        if self.chat_manager and hasattr(self.chat_manager, 'current_file'):
            project_id = getattr(self.chat_manager, 'current_file', None)
            logging.logger.debug(f"Using project/chat ID: {project_id}")

        resolved_params = {}
        resolved_model_name = self.active_model_name
        logging.logger.debug(f"Using globally selected model for request: '{resolved_model_name}'")

        if not resolved_model_name:
             logging.logger.error("FATAL: No active model name set during build_api_request_data!")
             raise ValueError("No active model selected.")

        if self.active_api_name and self.api_interface:
            state_data = self._read_state_file()
            api_settings_from_state = state_data.get("api_settings", {}).get(self.active_api_name, {})
            logging.logger.debug(f"Read settings from state for API '{self.active_api_name}': {api_settings_from_state}")

            api_config = self.api_interface.api_configs.get(self.active_api_name, {})
            default_params = api_config.get("generation_parameters", {})
            logging.logger.debug(f"Using default params from config for API '{self.active_api_name}': {default_params}")
            alterable_param_names = [s['name'] for s in api_config.get("alterable_settings", []) if 'name' in s]
            logging.logger.debug(f"Alterable parameters for '{self.active_api_name}': {alterable_param_names}")

            for key, default_value in default_params.items():
                value_from_state = api_settings_from_state.get(key)
                current_value = value_from_state if value_from_state is not None else default_value
                source = "state file" if value_from_state is not None else "API config default"

                try:
                    target_type = type(default_value) if default_value is not None else str
                    if target_type is float:
                        resolved_params[key] = float(current_value)
                        logging.logger.debug(f"  Param '{key}': Using value '{resolved_params[key]}' ({source}, converted to float)")
                    elif target_type is int:
                         resolved_params[key] = int(current_value)
                         logging.logger.debug(f"  Param '{key}': Using value '{resolved_params[key]}' ({source}, converted to int)")
                    elif target_type is bool:
                         resolved_params[key] = bool(current_value) # Simple bool conversion
                         logging.logger.debug(f"  Param '{key}': Using value '{resolved_params[key]}' ({source}, converted to bool)")
                    else: # Includes str and None default types
                         resolved_params[key] = str(current_value)
                         log_type = "str" if target_type is str else "str (default was None)"
                         logging.logger.debug(f"  Param '{key}': Using value '{resolved_params[key]}' ({source}, converted to {log_type})")
                except (ValueError, TypeError) as conv_e:
                     logging.logger.warning(f"  Param '{key}': Failed to convert value '{current_value}' ({source}) to type {target_type.__name__}. Using default '{default_value}'. Error: {conv_e}")
                     resolved_params[key] = default_value
        else:
            logging.logger.warning("Cannot resolve API params: Active API name or APIInterface missing.")
            resolved_params = {}

        request_data = {
            "messages": messages,
            "model_name": resolved_model_name,
            **resolved_params,
            "tools": None,
            "tool_choice": None,
            "persistent_uploads": False,
            "project_id": project_id,
        }
        logging.logger.debug(f"Final request_data constructed (excluding messages): "
                      f"Model='{request_data['model_name']}', "
                      f"Params={ {k:v for k,v in request_data.items() if k not in ['messages','model_name']} }")
        return request_data


    # Plugin Hooks (_get_plugin_name, _apply_..._hooks)
    # [ Remain the same ]
    def _get_plugin_name(self, plugin_instance):
        try:
            if hasattr(plugin_instance, 'config') and isinstance(plugin_instance.config, dict):
                return plugin_instance.config.get('name', type(plugin_instance).__name__)
            else:
                return type(plugin_instance).__name__
        except Exception:
            return "UnknownPlugin"

    def _apply_pre_history_hooks(self, input_text: str) -> Optional[str]:
        if not self.plugin_manager: return input_text
        current_text = input_text
        enabled_plugins = self.plugin_manager.get_enabled_plugins()
        extension_plugins = [p for p in enabled_plugins if self.plugin_manager.get_plugin_type(self._get_plugin_name(p)) == 'extension']
        for plugin in extension_plugins:
            plugin_name = self._get_plugin_name(plugin)
            if hasattr(plugin, 'pre_history') and callable(plugin.pre_history):
                try:
                    logging.logger.debug(f"Calling pre_history hook for plugin: {plugin_name}")
                    modified_text = plugin.pre_history(current_text)
                    if modified_text is None:
                        logging.logger.info(f"Plugin '{plugin_name}' pre_history hook requested stop (returned None).")
                        return None
                    current_text = modified_text
                except Exception as e:
                    logging.logger.exception(f"Error executing pre_history hook in plugin '{plugin_name}'. Skipping hook.")
        return current_text

    def _apply_pre_api_hooks(self, request_data: dict) -> Optional[dict]:
        if not self.plugin_manager: return request_data
        current_data = request_data
        enabled_plugins = self.plugin_manager.get_enabled_plugins()
        extension_plugins = [p for p in enabled_plugins if self.plugin_manager.get_plugin_type(self._get_plugin_name(p)) == 'extension']
        for plugin in extension_plugins:
            plugin_name = self._get_plugin_name(plugin)
            if hasattr(plugin, 'pre_api') and callable(plugin.pre_api):
                try:
                    logging.logger.debug(f"Calling pre_api hook for plugin: {plugin_name}")
                    modified_data = plugin.pre_api(current_data)
                    if modified_data is None:
                        logging.logger.info(f"Plugin '{plugin_name}' pre_api hook requested stop (returned None).")
                        return None
                    if not isinstance(modified_data, dict):
                         logging.logger.error(f"Plugin '{plugin_name}' pre_api hook returned non-dict type ({type(modified_data).__name__}). Discarding changes from this hook.")
                    else:
                         current_data = modified_data
                except Exception as e:
                    logging.logger.exception(f"Error executing pre_api hook in plugin '{plugin_name}'. Skipping hook.")
        return current_data

    def _apply_post_api_hooks(self, response_text: str, request_data: dict) -> Optional[str]:
        if not self.plugin_manager: return response_text
        current_text = response_text
        enabled_plugins = self.plugin_manager.get_enabled_plugins()
        extension_plugins = [p for p in enabled_plugins if self.plugin_manager.get_plugin_type(self._get_plugin_name(p)) == 'extension']
        for plugin in extension_plugins:
            plugin_name = self._get_plugin_name(plugin)
            if hasattr(plugin, 'post_api') and callable(plugin.post_api):
                try:
                    logging.logger.debug(f"Calling post_api hook for plugin: {plugin_name}")
                    modified_text = plugin.post_api(current_text, request_data)
                    if modified_text is None:
                        logging.logger.info(f"Plugin '{plugin_name}' post_api hook requested stop (returned None).")
                        return None
                    current_text = modified_text
                except Exception as e:
                    logging.logger.exception(f"Error executing post_api hook in plugin '{plugin_name}'. Skipping hook.")
        return current_text

    def _apply_post_history_hooks(self, chat_history: list) -> Optional[list]:
        if not self.plugin_manager: return chat_history
        current_history = chat_history
        enabled_plugins = self.plugin_manager.get_enabled_plugins()
        extension_plugins = [p for p in enabled_plugins if self.plugin_manager.get_plugin_type(self._get_plugin_name(p)) == 'extension']
        for plugin in extension_plugins:
            plugin_name = self._get_plugin_name(plugin)
            if hasattr(plugin, 'post_history') and callable(plugin.post_history):
                try:
                    logging.logger.debug(f"Calling post_history hook for plugin: {plugin_name}")
                    modified_history = plugin.post_history(list(current_history))
                    if modified_history is None:
                        logging.logger.info(f"Plugin '{plugin_name}' post_history hook requested stop (returned None).")
                        return None
                    if not isinstance(modified_history, list):
                         logging.logger.error(f"Plugin '{plugin_name}' post_history hook returned non-list type ({type(modified_history).__name__}). Discarding changes from this hook.")
                    else:
                         current_history = modified_history
                except Exception as e:
                    logging.logger.exception(f"Error executing post_history hook in plugin '{plugin_name}'. Skipping hook.")
        return current_history

    # Chat Management Passthrough
    # [ Remain the same ]
    def create_new_chat(self):
        logging.logger.info("Requesting new chat creation.")
        if self.chat_manager and hasattr(self.chat_manager, 'create_new_chat'):
             try:
                  self.chat_manager.create_new_chat()
                  self.clearDisplayRequest.emit()
                  logging.logger.info("New chat created successfully.")
             except Exception as e:
                  logging.logger.exception("Error during create_new_chat")
                  self.showMessageRequest.emit({"title": "Error", "message": f"Failed to create new chat:\n{e}", "icon": "critical"})
        else:
             logging.logger.error("Cannot create new chat: Chat/Project Manager not available or lacks 'create_new_chat' method.")
             self.showMessageRequest.emit({"title": "Error", "message": "Chat management component is unavailable.", "icon": "warning"})

    def load_chat(self, chat_id):
        logging.logger.warning(f"load_chat('{chat_id}') called - Not fully implemented yet.")
        if self.chat_manager and hasattr(self.chat_manager, 'load_chat'):
            try:
                success = self.chat_manager.load_chat(chat_id)
                if success:
                     self.clearDisplayRequest.emit()
                     logging.logger.info(f"Chat '{chat_id}' loaded.")
                else:
                     self.showMessageRequest.emit({"title": "Load Error", "message": f"Could not find or load chat '{chat_id}'.", "icon": "warning"})
            except Exception as e:
                logging.logger.exception(f"Error loading chat '{chat_id}'")
                self.showMessageRequest.emit({"title": "Load Error", "message": f"Failed to load chat '{chat_id}':\n{e}", "icon": "critical"})
        else:
             logging.logger.error("Cannot load chat: Chat/Project Manager unavailable or lacks 'load_chat'.")

    def delete_chat(self, chat_id):
        logging.logger.warning(f"delete_chat('{chat_id}') called - Not fully implemented yet.")
        if self.chat_manager and hasattr(self.chat_manager, 'delete_chat'):
             pass
        else:
            logging.logger.error("Cannot delete chat: Chat/Project Manager unavailable or lacks 'delete_chat'.")

    # User Selection
    def set_user_selection(self, api_name: str, model_name: str):
        # [ Remains the same ]
        if not api_name or not model_name:
             logging.logger.warning(f"Attempted to set invalid selection: API='{api_name}', Model='{model_name}'")
             return

        state_data = self._read_state_file()
        state_changed_flag = False

        if "active_api" not in state_data: state_data["active_api"] = None
        if "active_model" not in state_data: state_data["active_model"] = None
        if "api_settings" not in state_data or not isinstance(state_data["api_settings"], dict):
             state_data["api_settings"] = {}

        if self.active_api_name != api_name:
            logging.logger.info(f"Setting active API globally: '{api_name}' (was '{self.active_api_name}')")
            self.active_api_name = api_name
            state_data["active_api"] = api_name
            state_changed_flag = True

        if self.active_model_name != model_name:
             logging.logger.info(f"Setting active Model globally: '{model_name}' (was '{self.active_model_name}')")
             self.active_model_name = model_name
             state_data["active_model"] = model_name
             state_changed_flag = True

        if api_name not in state_data["api_settings"] or not isinstance(state_data["api_settings"][api_name], dict):
             state_data["api_settings"][api_name] = {}

        if state_data["api_settings"][api_name].get("selected_model") != model_name:
            logging.logger.info(f"Updating 'selected_model' for API '{api_name}' in state settings block to: '{model_name}'")
            state_data["api_settings"][api_name]["selected_model"] = model_name
            state_changed_flag = True

        if state_changed_flag:
             self._write_state_file(state_data)
             logging.logger.debug("State file saved due to selection change.")
        else:
             logging.logger.info(f"Selection unchanged or only memory update needed: API='{api_name}', Model='{model_name}'")

    # Plugin UI Interaction
    def request_ui_widget_insertion(self, zone_name: str, widget: 'QWidget', extension_plugin_name: str):
        # [ Remains the same ]
        logging.logger.info(f"Plugin '{extension_plugin_name}' requested widget insertion into zone '{zone_name}'.")
        if self.ui and hasattr(self.ui, 'add_widget_to_zone'):
            try:
                self.ui.add_widget_to_zone(zone_name, widget, extension_plugin_name)
                logging.logger.debug(f"Delegated widget insertion request to UI: {type(self.ui).__name__}")
            except NotImplementedError:
                 logging.logger.warning(f"Active UI '{type(self.ui).__name__}' does not implement 'add_widget_to_zone'.")
            except Exception as e:
                 logging.logger.exception(f"Error delegating widget insertion to UI '{type(self.ui).__name__}'.")
        else:
            logging.logger.warning("Cannot handle widget insertion: No active UI or UI lacks 'add_widget_to_zone' method.")