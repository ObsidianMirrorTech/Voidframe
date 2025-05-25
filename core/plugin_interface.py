# C:/Users/obsid/Desktop/AI Projects/Voidframe_0.3/core/plugin_interface.py
from abc import ABC, abstractmethod

class PluginInterface(ABC):
    """
    Defines the interface for standard plugins that hook into the data flow.
    """

    # Add @abstractmethod decorator if you want to force subclasses to implement,
    # otherwise, provide default pass-through implementations.
    # Using default implementations makes it easier for plugins to only implement hooks they need.

    def pre_history(self, input_text: str) -> str:
        """
        Called immediately after the user enters input, before it's added to chat history.
        Plugins can modify the user input here.
        Returns the (possibly modified) input text.
        """
        return input_text # Default implementation does nothing

    def pre_api(self, prompt: dict) -> dict:
        """
        Called after the chat history is assembled and before the request is sent to the API.
        Plugins can modify the prompt JSON.
        Returns the (possibly modified) prompt dictionary.
        """
        return prompt # Default implementation does nothing

    def post_api(self, response_text: str, prompt: dict) -> str:
        """
        Called immediately after receiving the API response but before it's processed further.
        Plugins can modify the raw response.
        Returns the (possibly modified) response text.
        """
        return response_text # Default implementation does nothing

    def post_history(self, chat_history: list) -> list:
        """
        Called after the API response has been appended to the chat history (but before saving).
        Plugins can modify the chat history.
        Returns the (possibly modified) chat history.
        """
        # Return a copy by default to prevent accidental mutation if not overridden
        return list(chat_history)

    # --- Optional Lifecycle Methods (Example - Add if implementing Improvement #5) ---
    # def on_load(self, data_router):
    #     """Called after all plugins are loaded."""
    #     pass
    #
    # def on_unload(self):
    #     """Called just before application exit or plugin unload."""
    #     pass

    # --- Optional Config Widget Method (Example - Add if implementing Improvement #1) ---
    # def get_config_widget(self):
    #     """Returns a QWidget for plugin configuration, or None."""
    #     return None
    #
    # def save_config(self):
    #      """Called when the main config window's save button is pressed."""
    #      pass