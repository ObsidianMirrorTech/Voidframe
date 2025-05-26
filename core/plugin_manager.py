import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget, QCheckBox, QLabel # Keep relevant Qt imports
from core.env import ROOT_DIR
from core import logging
from core import json_rpc # Added
import time             # Added
import uuid             # Added

class PluginManager:
    DEFAULT_PLUGIN_TIMEOUT = 10  # seconds (Added)

    def __init__(self, data_router, project_config: dict):
        self.data_router = data_router
        self.project_config = project_config
        self.plugin_procs = {}
        self.plugin_configs = {}
        self.plugin_types = {}
        self.plugin_paths = {}
        self.plugin_stderr_threads = {}
        self.load_all_plugins()

    def __del__(self):
        logging.logger.info("PluginManager is being deleted, shutting down all plugins.")
        self.shutdown_all_plugins()

    def _read_stderr(self, plugin_name: str, stderr_pipe):
        try:
            for line in iter(stderr_pipe.readline, ''):
                if line:
                    logging.logger.error(f"[{plugin_name}-stderr] {line.strip()}")
            if not stderr_pipe.closed:
                 stderr_pipe.close()
        except ValueError:
            logging.logger.warning(f"Stderr pipe for {plugin_name} likely closed.")
        except Exception as e:
            logging.logger.error(f"Exception in _read_stderr for {plugin_name}: {e}")
        finally:
            logging.logger.info(f"Stderr monitoring thread for {plugin_name} finished.")

    def shutdown_all_plugins(self):
        logging.logger.info(f"Shutting down all plugins. Current processes: {list(self.plugin_procs.keys())}")
        plugin_names = list(self.plugin_procs.keys())
        for plugin_name in plugin_names:
            proc_info = self.plugin_procs.get(plugin_name)
            if proc_info:
                logging.logger.info(f"Terminating plugin: {plugin_name}")
                process = proc_info['process']
                if proc_info['stdin'] and not proc_info['stdin'].closed:
                    try: proc_info['stdin'].close()
                    except Exception as e: logging.logger.error(f"Error closing stdin for {plugin_name}: {e}")
                if process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=2)
                        logging.logger.info(f"Plugin {plugin_name} terminated.")
                    except subprocess.TimeoutExpired:
                        logging.logger.warning(f"Plugin {plugin_name} did not terminate gracefully, killing.")
                        process.kill()
                        try: process.wait(timeout=1)
                        except subprocess.TimeoutExpired: logging.logger.error(f"Plugin {plugin_name} did not die after SIGKILL.")
                    except Exception as e: logging.logger.error(f"Error during termination of {plugin_name}: {e}")
                else: logging.logger.info(f"Plugin {plugin_name} already terminated (code {process.returncode}).")
                for pipe_name in ['stdout', 'stderr']:
                    pipe = proc_info.get(pipe_name)
                    if pipe and not pipe.closed:
                        try: pipe.close()
                        except Exception as e: logging.logger.error(f"Error closing {pipe_name} for {plugin_name}: {e}")
            thread = self.plugin_stderr_threads.pop(plugin_name, None)
            if thread and thread.is_alive():
                logging.logger.info(f"Joining stderr thread for {plugin_name}...")
                thread.join(timeout=1)
                if thread.is_alive(): logging.logger.warning(f"Stderr thread for {plugin_name} did not join.")
        self.plugin_procs.clear(); self.plugin_configs.clear(); self.plugin_types.clear(); self.plugin_paths.clear(); self.plugin_stderr_threads.clear()
        logging.logger.info("All plugins shut down and resources cleared.")

    def load_all_plugins(self):
        self.shutdown_all_plugins()
        interfaces_rel_path = self.project_config.get("plugins_interfaces_dir", "plugins/interfaces")
        extensions_rel_path = self.project_config.get("plugins_extensions_dir", "plugins/extensions")
        interfaces_abs_path = ROOT_DIR / interfaces_rel_path
        extensions_abs_path = ROOT_DIR / extensions_rel_path
        self._load_plugins_from_subdir(interfaces_abs_path, 'interface')
        self._load_plugins_from_subdir(extensions_abs_path, 'extension')
        logging.logger.info(f"Plugins loaded: {list(self.plugin_procs.keys())}")

    def _load_plugins_from_subdir(self, subdir_path: Path, plugin_type: str):
        if not subdir_path.is_dir():
            logging.logger.warning(f"Plugin subdir not found: {subdir_path}")
            return
        logging.logger.info(f"Scanning for {plugin_type} plugins in: {subdir_path}")
        for item in subdir_path.iterdir():
            if item.is_dir():
                plugin_folder_name = item.name; plugin_full_path = item
                config_path = plugin_full_path / "config.json"; plugin_file = plugin_full_path / "plugin.py"
                if not config_path.is_file(): logging.logger.warning(f"Skipping '{plugin_folder_name}': Missing config.json"); continue
                if not plugin_file.is_file(): logging.logger.warning(f"Skipping '{plugin_folder_name}': Missing plugin.py"); continue
                try:
                    with config_path.open('r', encoding='utf-8') as f: config = json.load(f)
                    effective_plugin_name = config.get("name", plugin_folder_name)
                    if effective_plugin_name in self.plugin_procs: logging.logger.error(f"Collision: '{effective_plugin_name}' loaded. Skip {plugin_full_path}"); continue
                except Exception as e: logging.logger.error(f"Error loading config for '{plugin_folder_name}': {e}", exc_info=True); continue
                try:
                    plugin_main_class = config.get("main_class", "PluginBase")
                    cmd = [sys.executable, str(ROOT_DIR / "core" / "plugin_executor.py"), str(subdir_path), plugin_folder_name, plugin_main_class]
                    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    logging.logger.info(f"Launching '{effective_plugin_name}': {' '.join(cmd)}")
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', creationflags=creationflags, bufsize=1)
                    self.plugin_procs[effective_plugin_name] = {'process': proc, 'stdin': proc.stdin, 'stdout': proc.stdout, 'stderr': proc.stderr}
                    self.plugin_configs[effective_plugin_name] = config; self.plugin_types[effective_plugin_name] = plugin_type; self.plugin_paths[effective_plugin_name] = plugin_full_path
                    thread = threading.Thread(target=self._read_stderr, args=(effective_plugin_name, proc.stderr), daemon=True)
                    thread.start(); self.plugin_stderr_threads[effective_plugin_name] = thread
                    logging.logger.info(f"Launched {plugin_type} plugin: '{effective_plugin_name}' (PID: {proc.pid})")
                except Exception as e:
                    logging.logger.exception(f"Failed to launch plugin '{effective_plugin_name}' from {plugin_full_path}")
                    if 'proc' in locals() and proc.poll() is None: proc.kill(); proc.wait()
                    if effective_plugin_name in self.plugin_procs: del self.plugin_procs[effective_plugin_name]

    def list_plugins(self, plugin_type: str = None):
        if plugin_type: return [name for name, p_type in self.plugin_types.items() if p_type == plugin_type and name in self.plugin_procs]
        else: return list(self.plugin_procs.keys())

    def get_plugin(self, plugin_name): return self.plugin_procs.get(plugin_name)
    def get_plugin_type(self, plugin_name): return self.plugin_types.get(plugin_name)
    def get_plugin_config(self, plugin_name): return self.plugin_configs.get(plugin_name)
    def get_enabled_plugins(self): return list(self.plugin_procs.values())

    def call_plugin_method(self, plugin_name: str, method: str, params: dict = None, timeout_override: int = None):
        proc_info = self.plugin_procs.get(plugin_name)
        request_id = str(uuid.uuid4())

        if not proc_info:
            logging.logger.error(f"Plugin '{plugin_name}' not found or not loaded.")
            return json_rpc.create_error_response(request_id, json_rpc.METHOD_NOT_FOUND, f"Plugin '{plugin_name}' not found or not running.")

        process = proc_info['process']; stdin_pipe = proc_info['stdin']; stdout_pipe = proc_info['stdout']

        if process.poll() is not None:
            logging.logger.error(f"Plugin '{plugin_name}' process (PID: {process.pid}) terminated (code: {process.returncode}).")
            return json_rpc.create_error_response(request_id, json_rpc.PLUGIN_ERROR, f"Plugin '{plugin_name}' process not running.")

        current_timeout = timeout_override if timeout_override is not None else self.DEFAULT_PLUGIN_TIMEOUT
        request_obj = json_rpc.create_request(method, params, request_id)
        serialized_request = json_rpc.serialize_message(request_obj)
        
        response_str = None
        try:
            logging.logger.debug(f"To '{plugin_name}' (PID {process.pid}): {serialized_request}")
            if stdin_pipe.closed:
                logging.logger.error(f"Stdin pipe closed for plugin '{plugin_name}'. Cannot call '{method}'.")
                return json_rpc.create_error_response(request_id, json_rpc.PLUGIN_ERROR, "Plugin stdin pipe closed.")
            stdin_pipe.write(serialized_request + '\n'); stdin_pipe.flush()

            start_time = time.monotonic()
            while time.monotonic() - start_time < current_timeout:
                if stdout_pipe.closed:
                    logging.logger.error(f"Stdout pipe closed for plugin '{plugin_name}' during call to '{method}'.")
                    return json_rpc.create_error_response(request_id, json_rpc.PLUGIN_ERROR, "Plugin stdout pipe closed.")
                
                response_str = stdout_pipe.readline().strip()
                if response_str: logging.logger.debug(f"From '{plugin_name}': {response_str}"); break
                
                if process.poll() is not None: # Check if plugin died during our read attempt
                    logging.logger.error(f"Plugin '{plugin_name}' terminated during call to '{method}' while awaiting response.")
                    return json_rpc.create_error_response(request_id, json_rpc.PLUGIN_ERROR, "Plugin terminated during call.")
                time.sleep(0.05) 
            else: # Timeout
                logging.logger.warning(f"Timeout ({current_timeout}s) calling '{method}' on '{plugin_name}'. PID: {process.pid}")
                return json_rpc.create_error_response(request_id, json_rpc.PLUGIN_TIMEOUT, f"Timeout on plugin '{plugin_name}'.")

            if not response_str: # Should be caught by timeout, but safeguard
                logging.logger.error(f"No response from '{plugin_name}' for '{method}'.")
                return json_rpc.create_error_response(request_id, json_rpc.PLUGIN_ERROR, "No response from plugin.")

            response_data = json_rpc.deserialize_message(response_str)
            if response_data.get("id") != request_id: logging.logger.warning(f"Mismatched ID from '{plugin_name}'. Expected {request_id}, got {response_data.get('id')}.")
            if "error" in response_data: logging.logger.error(f"Plugin '{plugin_name}' error for '{method}': {response_data['error']}"); return response_data
            if "result" in response_data: return response_data["result"]
            logging.logger.error(f"Invalid response from '{plugin_name}' for '{method}': missing 'result'. Resp: {response_data}")
            return json_rpc.create_error_response(request_id, json_rpc.INTERNAL_ERROR, "Invalid response from plugin.", {"raw_response": response_str})
        except json.JSONDecodeError as e:
            logging.logger.error(f"JSON decode error from '{plugin_name}': {e}. Raw: '{str(response_str)}'")
            return json_rpc.create_error_response(request_id, json_rpc.PARSE_ERROR, "Bad JSON from plugin.", {"raw_response": str(response_str)})
        except BrokenPipeError as e:
            logging.logger.error(f"Broken pipe with '{plugin_name}' (method: '{method}'): {e}. Process poll: {process.poll()}")
            return json_rpc.create_error_response(request_id, json_rpc.PLUGIN_ERROR, f"Broken pipe with '{plugin_name}'.")
        except Exception as e:
            logging.logger.exception(f"Generic error calling '{method}' on '{plugin_name}': {e}")
            return json_rpc.create_error_response(request_id, json_rpc.INTERNAL_ERROR, f"Host error calling '{plugin_name}': {str(e)}")

# Example usage (commented out)
# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO)
#     print("Initializing PluginManager...")
#     pm_config = { "plugins_interfaces_dir": "plugins/interfaces", "plugins_extensions_dir": "plugins/extensions" }
#     # Create dummy plugin dirs/files for testing if needed
#     # (Path(ROOT_DIR) / "plugins/interfaces/example_plugin").mkdir(parents=True, exist_ok=True)
#     # with open(Path(ROOT_DIR) / "plugins/interfaces/example_plugin/config.json", "w") as f: json.dump({"name": "Example", "main_class": "PluginBase"}, f)
#     # with open(Path(ROOT_DIR) / "plugins/interfaces/example_plugin/plugin.py", "w") as f: f.write("class PluginBase:
  def __init__(self, path, config):
    print('Example plugin init')
  def my_method(self, text):
    return f'Plugin received: {{text}}'")
#     plugin_manager = PluginManager(None, pm_config)
#     print(f"Loaded plugins: {plugin_manager.list_plugins()}")
#     if "Example" in plugin_manager.list_plugins():
#        print("Calling my_method on Example plugin...")
#        result = plugin_manager.call_plugin_method("Example", "my_method", {"text": "Hello from PluginManager"})
#        print(f"Result from plugin: {result}")
#     try: import time; time.sleep(2) # Let threads run
#     finally: print("Shutting down PluginManager..."); plugin_manager.shutdown_all_plugins(); print("PluginManager shut down.")
