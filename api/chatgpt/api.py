import os
import json
import openai
from core import logging
from typing import Dict, Any, Optional

class ChatGPTAdapter:
    """Adapter for interacting with OpenAI's Chat Completion API."""

    def __init__(self, api_config: dict, projects_base_path: str):
        self.api_config = api_config
        self.projects_base_path = projects_base_path
        self.client: Optional[openai.Client] = self._initialize_client()
        logging.logger.info("ChatGPT Adapter Initialized")

    def _initialize_client(self) -> Optional[openai.Client]:
        # ... (implementation unchanged) ...
        api_key = os.environ.get("OPENAI_API_KEY");
        if not api_key: logging.logger.error("OPENAI_API_KEY needed"); return None
        try: client=openai.Client(api_key=api_key); logging.logger.debug("OpenAI client created"); return client
        except Exception as e: logging.logger.exception("Failed init OpenAI client"); return None

    def run_inference(self, request_data: dict) -> str:
        """ Processes the inference request using parameters from request_data. """
        if not self.client: raise ConnectionError("OpenAI client not initialized.")

        # --- Extract Model and Parameters DIRECTLY from request_data ---
        # DataRouter is now responsible for providing resolved values
        model_name = request_data.get("model_name")
        temperature = request_data.get("temperature")
        top_p = request_data.get("top_p")
        max_tokens = request_data.get("max_output_tokens") # Use the key provided in request_data
        messages_for_api = request_data.get("messages", [])
        # Add others as needed: presence_penalty = request_data.get("presence_penalty")

        # --- Validation / Type Conversion (Essential Here) ---
        if not model_name: raise ValueError("Missing 'model_name' in request_data")
        if not messages_for_api: raise ValueError("Missing 'messages' in request_data")
        try: # Ensure parameters have valid types, provide safe fallbacks if conversion fails
            temperature = float(temperature) if temperature is not None else 0.7 # Default fallback
            top_p = float(top_p) if top_p is not None else 0.95
            max_tokens = int(max_tokens) if max_tokens is not None else 1024
            # Convert others...
        except (ValueError, TypeError) as e:
             logging.error(f"Invalid parameter type in request_data: {e}. Using defaults.")
             # Apply safe defaults if conversion fails
             temperature = 0.7; top_p = 0.95; max_tokens = 1024
             # Consider raising error instead?

        logging.logger.debug(f"ChatGPT Adapter: Using model='{model_name}', temp={temperature}, max_tokens={max_tokens}")

        # Tool Processing (Deferred)

        # --- API Call ---
        try:
            logging.logger.debug(f"Calling OpenAI API: model={model_name}")
            response = self.client.chat.completions.create(
                model=model_name,
                messages=messages_for_api,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                # Add other parameters here
            )

            # Response Handling (unchanged)
            response_content = response.choices[0].message.content
            logging.logger.debug("OpenAI Response received.")
            return response_content.strip() if response_content else ""

        # Exception Handling (unchanged)
        except openai.APIConnectionError as e: raise ConnectionError(f"OpenAI connection error: {e}") from e
        # ... other specific openai exceptions ...
        except Exception as e: raise RuntimeError(f"OpenAI API Error: {e}") from e


    def update_config(self, new_api_config: dict):
         """Updates the adapter's internal configuration (e.g., default model)."""
         logging.logger.info("ChatGPT Adapter updating config.")
         self.api_config = new_api_config


# Factory Function (unchanged)
def get_adapter_instance(api_config: dict, projects_base_path: str) -> ChatGPTAdapter:
     return ChatGPTAdapter(api_config, projects_base_path)