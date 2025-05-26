import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget, QCheckBox, QLabel # Keep relevant Qt imports if still needed by other parts of PluginManager
from core.env import ROOT_DIR
from core import logging

class PluginManager:
    def __init__(self, data_router, project_config: dict):
        self.data_router = data_router
        self.project_config = project_config
        self.plugin_procs = {}  # Stores {'process': Popen, 'stdin': stdin_pipe, 'stdout': stdout_pipe, 'stderr': stderr_pipe}
        self.plugin_configs = {}
        self.plugin_types = {}
        self.plugin_paths = {}
        self.plugin_stderr_threads = {}
        self.load_all_plugins()

    def __del__(self):
        logging.logger.info("PluginManager is being deleted, shutting down all plugins.")
        self.shutdown_all_plugins()

    def _read_stderr(self, plugin_name: str, stderr_pipe):
        """Reads and logs stderr output from a plugin subprocess."""
        try:
            for line in iter(stderr_pipe.readline, ''):
                if line:
                    logging.logger.error(f"[{plugin_name}-stderr] {line.strip()}")
            stderr_pipe.close() # Ensure pipe is closed when readline returns empty string (EOF)
        except Exception as e:
            logging.logger.error(f"Exception in _read_stderr for {plugin_name}: {e}")
        finally:
            logging.logger.info(f"Stderr monitoring thread for {plugin_name} finished.")


    def shutdown_all_plugins(self):
        """Terminates all running plugin subprocesses and cleans up resources."""
        logging.logger.info(f"Shutting down all plugins. Current processes: {list(self.plugin_procs.keys())}")
        plugin_names = list(self.plugin_procs.keys()) # Iterate over a copy of keys

        for plugin_name in plugin_names:
            proc_info = self.plugin_procs.get(plugin_name)
            if proc_info:
                logging.logger.info(f"Terminating plugin: {plugin_name}")
                process = proc_info['process']
                
                # Close stdin first to signal no more input
                if proc_info['stdin'] and not proc_info['stdin'].closed:
                    try:
                        proc_info['stdin'].close()
                    except Exception as e:
                        logging.logger.error(f"Error closing stdin for {plugin_name}: {e}")

                if process.poll() is None:  # Check if process is still running
                    try:
                        process.terminate() # SIGTERM
                        process.wait(timeout=2) # Wait for graceful shutdown
                        logging.logger.info(f"Plugin {plugin_name} terminated.")
                    except subprocess.TimeoutExpired:
                        logging.logger.warning(f"Plugin {plugin_name} did not terminate gracefully, killing (SIGKILL).")
                        process.kill() # SIGKILL
                        try:
                            process.wait(timeout=1) # Wait for kill
                        except subprocess.TimeoutExpired:
                            logging.logger.error(f"Plugin {plugin_name} did not die even after SIGKILL.")
                    except Exception as e:
                        logging.logger.error(f"Error during termination of {plugin_name}: {e}")
                else:
                    logging.logger.info(f"Plugin {plugin_name} was already terminated (return code {process.returncode}).")

                # Ensure other pipes are closed if they exist and are open
                for pipe_name in ['stdout', 'stderr']:
                    pipe = proc_info.get(pipe_name)
                    if pipe and not pipe.closed:
                        try:
                            pipe.close()
                        except Exception as e:
                            logging.logger.error(f"Error closing {pipe_name} for {plugin_name}: {e}")
            
            # Join the stderr thread
            thread = self.plugin_stderr_threads.pop(plugin_name, None)
            if thread and thread.is_alive():
                logging.logger.info(f"Joining stderr thread for {plugin_name}...")
                thread.join(timeout=1)
                if thread.is_alive():
                    logging.logger.warning(f"Stderr thread for {plugin_name} did not join in time.")
        
        self.plugin_procs.clear()
        self.plugin_configs.clear()
        self.plugin_types.clear()
        self.plugin_paths.clear()
        # self.plugin_stderr_threads should be clear if pop was successful
        logging.logger.info("All plugins shut down and resources cleared.")


    def load_all_plugins(self):
        """Loads plugins from directories specified in project_config."""
        self.shutdown_all_plugins() # Clean up any existing plugins first

        # Get directories from config, relative to ROOT_DIR
        interfaces_rel_path = self.project_config.get("plugins_interfaces_dir", "plugins/interfaces")
        extensions_rel_path = self.project_config.get("plugins_extensions_dir", "plugins/extensions")

        interfaces_abs_path = ROOT_DIR / interfaces_rel_path
        extensions_abs_path = ROOT_DIR / extensions_rel_path

        self._load_plugins_from_subdir(interfaces_abs_path, 'interface')
        self._load_plugins_from_subdir(extensions_abs_path, 'extension')

        logging.logger.info(f"Plugins loaded: {list(self.plugin_procs.keys())}")

    def _load_plugins_from_subdir(self, subdir_path: Path, plugin_type: str):
        """Loads all valid plugins from a specific subdirectory Path by launching them as subprocesses."""
        if not subdir_path.is_dir():
            logging.logger.warning(f"Plugin subdirectory not found or not a directory: {subdir_path}")
            return

        logging.logger.info(f"Scanning for {plugin_type} plugins in: {subdir_path}")
        for item in subdir_path.iterdir():
            if item.is_dir():
                plugin_folder_name = item.name
                plugin_full_path = item

                config_path = plugin_full_path / "config.json"
                plugin_file = plugin_full_path / "plugin.py" # Used for validation, not direct import

                if not config_path.is_file():
                    logging.logger.warning(f"Skipping '{plugin_folder_name}' in {subdir_path}: Missing config.json")
                    continue
                if not plugin_file.is_file(): # Still good to check if plugin.py exists
                    logging.logger.warning(f"Skipping '{plugin_folder_name}' in {subdir_path}: Missing plugin.py")
                    continue

                try:
                    with config_path.open('r', encoding='utf-8') as f:
                        config = json.load(f)
                    effective_plugin_name = config.get("name", plugin_folder_name)

                    if effective_plugin_name in self.plugin_procs:
                        logging.logger.error(f"Plugin name collision: '{effective_plugin_name}' already loaded or being loaded. Skipping plugin at {plugin_full_path}")
                        continue
                except json.JSONDecodeError:
                    logging.logger.error(f"Failed to load config.json for '{plugin_folder_name}' in {subdir_path}: Invalid JSON.", exc_info=True)
                    continue
                except Exception as e:
                    logging.logger.error(f"Error loading config.json for '{plugin_folder_name}' in {subdir_path}: {e}", exc_info=True)
                    continue
                
                # TODO: Implement virtual environment creation and dependency installation
                # This would involve checking for a requirements.txt in plugin_full_path,
                # creating a venv (e.g., in plugin_full_path / '.venv'), and installing deps.
                # The sys.executable for the command below might then point to python in that venv.

                try:
                    # Determine the main class to load in the plugin executor
                    # For now, hardcoding to "PluginBase" as per current plugin structure
                    plugin_main_class = config.get("main_class", "PluginBase")

                    cmd = [
                        sys.executable, # Use the same Python interpreter that Voidframe is running under
                        str(ROOT_DIR / "core" / "plugin_executor.py"),
                        str(subdir_path), # Root path for this type of plugin (e.g., plugins/interfaces)
                        plugin_folder_name,    # The plugin's own directory name (e.g., my_ui_plugin)
                        plugin_main_class      # The class within plugin.py to instantiate
                    ]
                    
                    creationflags = 0
                    if sys.platform == "win32":
                        creationflags = subprocess.CREATE_NO_WINDOW

                    logging.logger.info(f"Launching plugin '{effective_plugin_name}' with command: {' '.join(cmd)}")
                    
                    proc = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True, # Use text mode for streams
                        encoding='utf-8', # Specify UTF-8 encoding
                        creationflags=creationflags
                    )

                    self.plugin_procs[effective_plugin_name] = {
                        'process': proc,
                        'stdin': proc.stdin,
                        'stdout': proc.stdout,
                        'stderr': proc.stderr # For the stderr reading thread
                    }
                    self.plugin_configs[effective_plugin_name] = config
                    self.plugin_types[effective_plugin_name] = plugin_type
                    self.plugin_paths[effective_plugin_name] = plugin_full_path

                    # Start a thread to read stderr for this plugin
                    stderr_thread = threading.Thread(
                        target=self._read_stderr,
                        args=(effective_plugin_name, proc.stderr),
                        daemon=True # Daemon threads exit when the main program exits
                    )
                    stderr_thread.start()
                    self.plugin_stderr_threads[effective_plugin_name] = stderr_thread

                    logging.logger.info(f"Successfully launched {plugin_type} plugin: '{effective_plugin_name}' (PID: {proc.pid})")

                except Exception as e:
                    logging.logger.exception(f"Failed to launch or setup subprocess for plugin '{effective_plugin_name}' from {plugin_full_path}")
                    # Clean up if proc was created but other setup failed
                    if 'proc' in locals() and proc.poll() is None:
                        proc.kill()
                        proc.wait()
                    if effective_plugin_name in self.plugin_procs:
                        del self.plugin_procs[effective_plugin_name]


    def list_plugins(self, plugin_type: str = None):
        if plugin_type:
            return [name for name, p_type in self.plugin_types.items() if p_type == plugin_type and name in self.plugin_procs]
        else:
            return list(self.plugin_procs.keys())

    def get_plugin(self, plugin_name):
        """Returns the process information dictionary for the named plugin."""
        return self.plugin_procs.get(plugin_name)

    def get_plugin_type(self, plugin_name):
        return self.plugin_types.get(plugin_name)

    def get_plugin_config(self, plugin_name):
        return self.plugin_configs.get(plugin_name)

    def get_enabled_plugins(self):
        """Returns a list of process information dictionaries for all loaded plugins."""
        return list(self.plugin_procs.values())

# Example of how PluginManager might be instantiated and cleaned up in your main application
# if __name__ == '__main__':
#     # Assuming ROOT_DIR and logging are configured
#     # Mock project_config and data_router for standalone testing
#     class MockDataRouter:
#         pass
#     
#     mock_project_config = {
#         "plugins_interfaces_dir": "plugins/interfaces",
#         "plugins_extensions_dir": "plugins/extensions" 
#     }
#     # Ensure plugin directories and a sample plugin exist for testing
#     # (e.g., plugins/interfaces/my_test_plugin/config.json and plugin.py)
#
#     logging.basicConfig(level=logging.INFO)
#     
#     print("Initializing PluginManager...")
#     plugin_manager = PluginManager(MockDataRouter(), mock_project_config)
#     
#     print(f"Loaded plugins: {plugin_manager.list_plugins()}")
#     # Keep it running for a bit to see stderr logs if any
#     try:
#         # In a real app, this would be the main event loop or a long-running process
#         import time
#         time.sleep(5) 
#     finally:
#         print("Shutting down PluginManager...")
#         plugin_manager.shutdown_all_plugins() # Explicit shutdown
#         # Alternatively, rely on __del__ if plugin_manager instance goes out of scope
#         print("PluginManager shut down.")
