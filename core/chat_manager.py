import os
import json
from core import logging  # Assuming logging is set up in core/logging.py

class ChatManager:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
        self.chat_dir = os.path.join(self.storage_dir, "chat_history")
        os.makedirs(self.chat_dir, exist_ok=True)
        self.chat_history = []
        self.current_file = None
        self.load_most_recent_chat()

    def load_most_recent_chat(self):
        # Scan the chat directory for files named like chat_001.json
        files = [f for f in os.listdir(self.chat_dir) if f.startswith("chat_") and f.endswith(".json")]
        if files:
            files.sort(key=lambda x: int(x.split("_")[1].split(".")[0]))
            self.current_file = files[-1]
            file_path = os.path.join(self.chat_dir, self.current_file)
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                self.chat_history = data.get("chat_history", [])
            except json.JSONDecodeError as e:
                logging.logger.error(f"Error decoding JSON in {file_path}: {e}. Creating a new chat file.")
                self.create_new_chat()
        else:
            self.create_new_chat()

    def create_new_chat(self):
        # Determine the next sequential number
        files = [f for f in os.listdir(self.chat_dir) if f.startswith("chat_") and f.endswith(".json")]
        if files:
            files.sort(key=lambda x: int(x.split("_")[1].split(".")[0]))
            next_num = int(files[-1].split("_")[1].split(".")[0]) + 1
        else:
            next_num = 1
        self.current_file = f"chat_{next_num:03d}.json"
        self.chat_history = []
        self.save_chat()

    def append_message(self, role, content):
        self.chat_history.append({"role": role, "content": content})
        self.save_chat()

    def get_chat_history(self):
        return self.chat_history

    def save_chat(self):
        data = {"chat_history": self.chat_history}
        with open(os.path.join(self.chat_dir, self.current_file), "w") as f:
            json.dump(data, f, indent=2)

    def delete_current_chat(self):
        if self.current_file:
            os.remove(os.path.join(self.chat_dir, self.current_file))
        self.chat_history = []
        self.current_file = None
        self.create_new_chat()
