import os
import json
import inspect # *** Import inspect ***
from google import genai
try:
    from google.genai import types as genai_types
    from google.genai import client as genai_client # Need client for types if using older version? Check imports
    from google.genai.types import GenerateContentResponse # Explicit import for type hint
except ImportError:
    try:
        import google.genai as genai_types # Fallback
        genai_client = None # Indicate client types might be missing
        GenerateContentResponse = Any # Fallback type hint
        from core import logging as cl # Use logger instance here too
        cl.logger.warning("Gemini types fallback. Some type hints might be inaccurate.")
    except ImportError:
        from core import logging as cl # Use logger instance here too
        cl.logger.error("Fatal: Failed to import google.genai library.")
        genai_types = None
        genai_client = None
        GenerateContentResponse = Any

from core import logging # Import the base logging setup
from typing import Dict, Any, Optional, List, Union # Added Union

class GeminiAdapter:
    def __init__(self, api_config: dict, projects_base_path: str):
        self.api_config = api_config
        self.projects_base_path = projects_base_path
        # Ensure genai_client type hint is valid or Any
        self.client: Optional[Union[genai_client.Client, Any]] = self._initialize_client()
        # Use logger instance
        logging.logger.info("Gemini Adapter Initialized (using Client pattern)")

        # *** Add Inspection Code (Keep this for debugging if needed) ***
        if self.client and hasattr(self.client, 'models') and hasattr(self.client.models, 'generate_content'):
            try:
                sig = inspect.signature(self.client.models.generate_content)
                # Use logger instance
                logging.logger.info(f"Detected signature for client.models.generate_content: {sig}")
                # print(f"DEBUG: Detected signature for client.models.generate_content: {sig}") # Optional console print
            except Exception as e:
                # Use logger instance
                logging.logger.error(f"Could not inspect client.models.generate_content signature: {e}")
                # print(f"ERROR: Could not inspect client.models.generate_content signature: {e}")
        elif self.client:
            # Use logger instance
            logging.logger.warning("Gemini client initialized, but 'client.models.generate_content' not found for inspection.")
            # print("WARNING: Gemini client initialized, but 'client.models.generate_content' not found for inspection.")
        else:
             # Use logger instance
             logging.logger.warning("Gemini client failed initialization, cannot inspect methods.")
             # print("WARNING: Gemini client failed initialization, cannot inspect methods.")


    def _initialize_client(self) -> Optional[Union[genai_client.Client, Any]]:
        if not genai: # Check if the core library import failed
             # Use logger instance
             logging.logger.critical("google.genai library failed to import. Cannot initialize client.")
             return None
        api_key = os.environ.get("GEMINI_API_KEY");
        if not api_key:
             # Use logger instance
             logging.logger.error("GEMINI_API_KEY environment variable not set. Cannot initialize Gemini client.")
             return None
        try:
             # Use the correct class if available
             client_class = getattr(genai, 'Client', None)
             if client_class:
                  client=client_class(api_key=api_key)
                  # Use logger instance
                  logging.logger.debug("genai.Client created successfully.")
                  return client
             else:
                  # Use logger instance
                  logging.logger.error("Failed to find genai.Client class.")
                  return None
        except AttributeError as ae:
             # Use logger instance
             logging.logger.error(f"AttributeError finding genai.Client (library structure changed?): {ae}", exc_info=True)
             return None
        except Exception as e:
             # Use logger instance
             logging.logger.exception(f"Failed to initialize genai.Client")
             return None

    # --- run_inference using config object ---
    def run_inference(self, request_data: dict) -> str:
        if not self.client:
            raise ConnectionError("Gemini client not initialized or failed to initialize.")
        if not genai_types:
            raise ImportError("Gemini type definitions (google.genai.types) failed to import.")

        model_name = request_data.get("model_name")
        # Get defaults from own config if missing in request_data
        default_params = self.api_config.get("generation_parameters", {})
        if not model_name:
             model_name = self.api_config.get("default_model")
             # Use logger instance
             logging.logger.warning(f"Model name missing in request_data, falling back to adapter default: {model_name}")
             if not model_name:
                  # Provide a hardcoded fallback if even the adapter default is missing
                  model_name = "gemini-1.5-flash"
                  # Use logger instance
                  logging.logger.error(f"Adapter default model missing in config, hardcoding fallback: {model_name}")


        # --- Parameter Extraction and Type Conversion ---
        try: # Perform type conversions with fallbacks
            temperature = float(request_data.get("temperature", default_params.get("temperature", 1.0)))
            top_p = float(request_data.get("top_p", default_params.get("top_p", 0.95)))
            top_k = int(request_data.get("top_k", default_params.get("top_k", 40)))
            max_output_tokens = int(request_data.get("max_output_tokens", default_params.get("max_output_tokens", 1024)))
            # Add other parameters here if they become part of the standard request_data
            # stop_sequences = request_data.get("stop_sequences") # Example
        except (ValueError, TypeError) as e:
            # Use logger instance
            logging.logger.error(f"Invalid Gemini parameter type in request_data: {e}. Using API defaults.")
            # Use defaults directly from config
            temperature=float(default_params.get("temperature",1.0))
            top_p=float(default_params.get("top_p",0.95))
            top_k=int(default_params.get("top_k",40))
            max_output_tokens=int(default_params.get("max_output_tokens",1024))
            # stop_sequences = default_params.get("stop_sequences") # Example

        # Use logger instance
        logging.logger.debug(f"Gemini Adapter: Using model='{model_name}', T={temperature}, P={top_p}, K={top_k}, MaxT={max_output_tokens}")

        # --- Model Name Formatting ---
        # Ensure model name has 'models/' prefix if needed by the API version being used
        # Assuming the client library handles this, but keeping check just in case
        if not model_name.startswith("models/"):
            model_name_for_api = f"models/{model_name}"
            # Use logger instance - THIS WAS THE LINE CAUSING THE ERROR
            logging.logger.debug(f"Prepending 'models/' to model name: {model_name_for_api}")
        else:
            model_name_for_api = model_name

        # --- Content Building ---
        # Translate Voidframe internal messages format to Gemini's 'contents' format
        api_contents: List[Union[genai_types.ContentDict, Dict[str, Any]]] = [] # Use ContentDict if available
        system_instruction_parts = []

        for msg in request_data.get("messages", []):
            role = msg.get("role")
            content = msg.get("content")
            files = msg.get("files") # Placeholder for future file handling

            if content is None and files is None: # Skip empty messages
                # Use logger instance
                logging.logger.debug(f"Skipping message with no content or files: Role={role}")
                continue

            # Prepare parts for the message (text and future files)
            message_parts: List[Union[genai_types.Part, str, Dict]] = [] # Use Part if available
            if content:
                try:
                     # Use Part.from_text if available and callable
                     if hasattr(genai_types, 'Part') and hasattr(genai_types.Part, 'from_text') and callable(genai_types.Part.from_text):
                          message_parts.append(genai_types.Part.from_text(text=content))
                     else:
                          message_parts.append(content) # Fallback to raw string if Part is missing/unusable
                          # logging.logger.error("genai_types.Part.from_text not available or callable.") # Log only once?
                except Exception as e:
                     # Use logger instance
                     logging.logger.error(f"Error creating text Part for Gemini content: {e}", exc_info=True)
                     message_parts.append(content) # Add raw string on error

            # TODO: Process 'files' here when file handling is implemented
            #       - Use upload_manager or similar logic
            #       - Append FileData or Part objects to message_parts

            if not message_parts: # Don't add empty messages
                 # Use logger instance
                 logging.logger.warning(f"Skipping message with role '{role}' as no valid parts could be generated.")
                 continue

            # Map roles and construct content dictionary
            if role == "assistant":
                api_contents.append({"role": "model", "parts": message_parts})
            elif role == "user":
                api_contents.append({"role": "user", "parts": message_parts})
            elif role == "system":
                # Gemini API (v1beta+) often uses a dedicated system_instruction field in config
                # Accumulate system message parts here, handle later
                system_instruction_parts.extend(message_parts)
                # Use logger instance
                logging.logger.debug("Added system message content to be used in system_instruction.")
            elif role == "tool":
                # TODO: Handle tool call results (FunctionResponse) - Phase 5+
                # Use logger instance
                logging.logger.warning(f"Skipping message with unhandled role: {role}")
                continue
            else:
                # Use logger instance
                logging.logger.warning(f"Skipping message with unknown role: {role}")
                continue

        if not api_contents and not system_instruction_parts:
             raise ValueError("No valid messages or system instruction could be constructed for the Gemini API call.")

        # --- Create GenerationConfig Object ---
        # Construct the configuration object expected by the API
        system_instruction_content = None
        if system_instruction_parts:
            # Combine system parts into a single Content object or dict if needed
            # For simplicity now, let's just join text parts if Part.from_text wasn't used
            if all(isinstance(p, str) for p in system_instruction_parts):
                 system_instruction_content = "\n".join(system_instruction_parts)
                 # Use logger instance
                 logging.logger.debug(f"Using combined system text: '{system_instruction_content[:100]}...'")
            elif hasattr(genai_types, 'Content'):
                 # If parts are proper Part objects, create a Content object
                 system_instruction_content = genai_types.Content(parts=system_instruction_parts, role="system") # Role here might not matter if passed to system_instruction param
                 # Use logger instance
                 logging.logger.debug("Using Content object for system_instruction.")
            else:
                 # Use logger instance
                 logging.logger.warning("Cannot reliably combine system instruction parts. Only using first text part.")
                 system_instruction_content = next((p for p in system_instruction_parts if isinstance(p, str)), None)


        generation_config_obj = None
        try:
             # Check if GenerateContentConfig type is available
             if hasattr(genai_types, 'GenerateContentConfig'):
                  config_dict = {
                      "temperature": temperature,
                      "top_p": top_p,
                      "top_k": top_k,
                      "max_output_tokens": max_output_tokens
                      # Add other parameters here if needed
                      # "stop_sequences": stop_sequences
                  }
                  # Add system_instruction if it was generated and GenerateContentConfig supports it
                  # (Check signature or docs - assuming it does based on documentation)
                  if system_instruction_content:
                      # Pass the Content object or string directly
                      config_dict["system_instruction"] = system_instruction_content

                  generation_config_obj = genai_types.GenerateContentConfig(**config_dict)
                  # Use logger instance
                  logging.logger.debug("Created GenerateContentConfig object.")
             else:
                  # Use logger instance
                  logging.logger.warning("genai_types.GenerateContentConfig not found. Cannot create config object.")
                  # If config object isn't possible, we might have to skip passing params,
                  # or try passing a dict (less likely to work based on signature).
                  # For now, proceed without it if the type is missing.

        except Exception as e:
             # Use logger instance
             logging.logger.exception("Error creating GenerateContentConfig for Gemini.")
             # Decide whether to raise or proceed without config

        # --- API Call ---
        # Pass the model, contents, and the config object
        try:
            # Use logger instance
            logging.logger.debug(f"Attempting Gemini API call to model '{model_name_for_api}'...")
            # Use logger instance
            logging.logger.debug(f"  Contents: {api_contents}") # Log structure being sent
            # Use logger instance
            logging.logger.debug(f"  Config: {generation_config_obj}") # Log config object

            # Make the API call using the arguments identified from the signature
            response: GenerateContentResponse = self.client.models.generate_content(
                model=model_name_for_api,
                contents=api_contents, # Should be List[ContentDict] or similar
                config=generation_config_obj # *** Use the correct parameter name: 'config' ***
                # TODO: Add 'tools' argument when implementing function calling
                # TODO: Add 'safety_settings' argument if needed
            )

            # --- Response Handling ---
            if not response:
                 # Use logger instance
                 logging.logger.error("Gemini API call returned None or empty response.")
                 raise RuntimeError("Gemini API returned no response.")

            # Accessing response text - check GenerateContentResponse structure
            # Common patterns: response.text, response.candidates[0].content.parts[0].text
            response_text = ""
            try:
                 if hasattr(response, 'text') and response.text:
                      response_text = response.text
                 elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                      # Combine text from all parts in the first candidate's content
                      response_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
                 else:
                      # Use logger instance
                      logging.logger.warning("Could not extract text from Gemini response using common attributes.")
                      # Maybe log the full response structure for debugging
                      try:
                           # Use logger instance
                           logging.logger.warning(f"Full Gemini response structure: {response}")
                      except Exception:
                           # Use logger instance
                           logging.logger.warning("Could not log full Gemini response structure.")
                      response_text = "[Error: Could not extract text]"

            except AttributeError as ae:
                 # Use logger instance
                 logging.logger.error(f"AttributeError accessing Gemini response text: {ae}. Response structure: {response}", exc_info=True)
                 response_text = "[Error: Response structure mismatch]"
            except Exception as e:
                 # Use logger instance
                 logging.logger.exception("Unexpected error processing Gemini response content.")
                 response_text = "[Error: Processing response failed]"

            # Use logger instance
            logging.logger.debug(f"Gemini Response received. Text length: {len(response_text)}")
            # logging.logger.debug(f"Gemini Full Response: {response}") # Optional: Log full response if needed
            return response_text.strip()

        # --- Exception Handling ---
        except TypeError as e:
            # This was the original error, should be fixed by using 'config='
            # Use logger instance
            logging.logger.exception(f"TypeError during Gemini API call (model={model_name_for_api}). Check arguments vs signature: {e}")
            raise RuntimeError(f"Gemini API parameter error: {e}") from e
        except AttributeError as e:
            # Could happen if self.client or self.client.models is None or structure changes
            # Use logger instance
            logging.logger.exception(f"AttributeError during Gemini API call (model={model_name_for_api}). Client structure issue? {e}")
            raise RuntimeError(f"Gemini client structure or method error: {e}") from e
        except ImportError as e:
            # If types were missing
            # Use logger instance
            logging.logger.exception(f"ImportError during Gemini API call. genai types missing? {e}")
            raise RuntimeError(f"Gemini library import error: {e}") from e
        except ValueError as e:
             # Raised if messages are invalid
             # Use logger instance
             logging.logger.exception(f"ValueError during Gemini API call (model={model_name_for_api}): {e}")
             raise RuntimeError(f"Invalid input data for Gemini API: {e}") from e
        except Exception as e:
            # Catch other potential API errors (network, auth, specific Google API errors)
            # TODO: Catch specific google.api_core.exceptions if possible
            # Use logger instance
            logging.logger.exception(f"Unexpected error during Gemini API call (model={model_name_for_api}): {e}")
            # Try to get more specific error info if available
            error_details = str(e)
            if hasattr(e, 'details'): error_details = f"{e} - Details: {e.details()}"
            raise RuntimeError(f"Gemini API Error: {error_details}") from e

    def update_config(self, new_api_config: dict):
        """Updates the adapter's internal configuration."""
        # Use logger instance
        logging.logger.info("Gemini Adapter updating config.")
        self.api_config = new_api_config
        # Re-initialization might be needed if API key or other critical connection params change
        # self.client = self._initialize_client() # Uncomment if re-init is necessary on config change

# --- Factory Function ---
def get_adapter_instance(api_config: dict, projects_base_path: str) -> GeminiAdapter:
     """Creates and returns an instance of the GeminiAdapter."""
     return GeminiAdapter(api_config, projects_base_path)