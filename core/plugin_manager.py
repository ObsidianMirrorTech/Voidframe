import importlib.util
import json
import os
from pathlib import Path # Use Path object for consistency
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget, QCheckBox, QLabel
from core.env import ROOT_DIR
from core import logging

class PluginManager:
    # Pass project_config during initialization
    def __init__(self, data_router, project_config: dict):
        self.data_router = data_router
        self.project_config = project_config # Store the project config
        self.plugins = {} # { plugin_name: plugin_instance }
        self.plugin_configs = {} # { plugin_name: config_dict }
        self.plugin_types = {} # { plugin_name: 'interface' | 'extension' }
        self.plugin_paths = {} # { plugin_name: Path object }
        self.load_all_plugins() # Load plugins on initialization

    def load_all_plugins(self):
        """Loads plugins from directories specified in project_config."""
        self.plugins = {}
        self.plugin_configs = {}
        self.plugin_types = {}
        self.plugin_paths = {}

        # Get directories from config, relative to ROOT_DIR
        interfaces_rel_path = self.project_config.get("plugins_interfaces_dir", "plugins/interfaces")
        extensions_rel_path = self.project_config.get("plugins_extensions_dir", "plugins/extensions")

        interfaces_abs_path = ROOT_DIR / interfaces_rel_path
        extensions_abs_path = ROOT_DIR / extensions_rel_path

        # Load from interfaces subdir
        self._load_plugins_from_subdir(interfaces_abs_path, 'interface')
        # Load from extensions subdir
        self._load_plugins_from_subdir(extensions_abs_path, 'extension')

        logging.logger.info(f"Plugins loaded: {list(self.plugins.keys())}")
        # TODO: Add call to trigger on_load for extensions (Phase 4)
        # self._trigger_plugin_on_load()

    def _load_plugins_from_subdir(self, subdir_path: Path, plugin_type: str):
        """Loads all valid plugins from a specific subdirectory Path."""
        if not subdir_path.is_dir():
            logging.logger.info(f"Plugin subdirectory not found or not a directory (this might be normal): {subdir_path}")
            return

        logging.logger.info(f"Scanning for {plugin_type} plugins in: {subdir_path}")
        for item in subdir_path.iterdir(): # Use iterdir for Path objects
            if item.is_dir():
                plugin_name = item.name # Use folder name as potential fallback
                plugin_path = item

                config_path = plugin_path / "config.json"
                plugin_file = plugin_path / "plugin.py"

                if not config_path.is_file():
                    logging.logger.warning(f"Skipping '{plugin_name}' in {subdir_path}: Missing config.json")
                    continue
                if not plugin_file.is_file():
                    logging.logger.warning(f"Skipping '{plugin_name}' in {subdir_path}: Missing plugin.py")
                    continue

                # --- Load Config ---
                try:
                    with config_path.open('r', encoding='utf-8') as f:
                        config = json.load(f)
                    effective_plugin_name = config.get("name", plugin_name)
                    if effective_plugin_name in self.plugins:
                        logging.logger.error(f"Plugin name collision: '{effective_plugin_name}' already loaded. Skipping plugin at {plugin_path}")
                        continue
                except json.JSONDecodeError:
                    logging.logger.error(f"Failed to load config.json for '{plugin_name}' in {subdir_path}: Invalid JSON.", exc_info=True)
                    continue
                except Exception as e:
                    logging.logger.error(f"Failed to load config.json for '{plugin_name}' in {subdir_path}: {e}", exc_info=True)
                    continue

                # --- Load Module ---
                try:
                    # Use a unique module name based on type and name to avoid collisions
                    module_name = f"voidframe.plugins.{plugin_type}.{plugin_name}"
                    spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                    if spec is None:
                         raise ImportError(f"Could not create module spec for {plugin_file}")
                    module = importlib.util.module_from_spec(spec)
                    # TODO: Consider adding plugin_path to sys.path temporarily? Might not be needed.
                    spec.loader.exec_module(module)

                    if hasattr(module, "PluginBase"):
                        # Pass plugin_path (Path object) and config
                        plugin_instance = module.PluginBase(plugin_path, config)

                        self.plugins[effective_plugin_name] = plugin_instance
                        self.plugin_configs[effective_plugin_name] = config
                        self.plugin_types[effective_plugin_name] = plugin_type
                        self.plugin_paths[effective_plugin_name] = plugin_path
                        logging.logger.info(f"Successfully loaded {plugin_type} plugin: '{effective_plugin_name}'")
                    else:
                         logging.logger.error(f"Plugin '{effective_plugin_name}' at {plugin_file} does not have a 'PluginBase' class.")
                except Exception as e:
                    logging.logger.exception(f"Failed to load or instantiate plugin '{effective_plugin_name}' from {plugin_path}")

    # --- Other methods remain the same ---
    def list_plugins(self, plugin_type: str = None):
        if plugin_type:
            return [name for name, p_type in self.plugin_types.items() if p_type == plugin_type]
        else:
            return list(self.plugins.keys())

    def get_plugin(self, plugin_name):
        return self.plugins.get(plugin_name)

    def get_plugin_type(self, plugin_name):
        return self.plugin_types.get(plugin_name)

    def get_plugin_config(self, plugin_name):
        return self.plugin_configs.get(plugin_name)

    def get_enabled_plugins(self):
        # Placeholder: Assumes all loaded plugins are enabled
        logging.logger.debug("get_enabled_plugins currently returns ALL loaded plugins.")
        return list(self.plugins.values())