
import re
from pathlib import Path

class ConfigParser:
    def __init__(self, config_path: Path):
        self.config_path = config_path

    def load_config(self):
        """
        Reads the config file and extracts specific variables.
        Returns a dictionary of key-value pairs.
        """
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                content = f.read()

            config_data = {}
            
            # Define regex for string variables (captures content inside quotes)
            # key = "value" or key = 'value'
            str_vars = ["PERSONA", "BACKEND", "LOCAL_MODEL", "AI_MODEL"]
            for key in str_vars:
                # Match: KEY = "VALUE"
                # \s*=\s*: handles spaces around =
                # (['"]): capture group 1 for quote type
                # (.*?): capture group 2 for value
                # \1: match matching closing quote
                pattern = re.compile(rf"^{key}\s*=\s*(['\"])(.*?)\1", re.MULTILINE)
                match = pattern.search(content)
                if match:
                    config_data[key] = match.group(2)
                else:
                    config_data[key] = "" # Default if not found

            # Define regex for boolean variables
            # key = True or key = False
            bool_vars = ["VOICE", "THINKING_SUPPORT", "FUNCTION_CALLING_SUPPORT", "OLLAMA_CLOUD", 
                         "VERTEX", "PAST_MEMORY", "CONTEXT_CACHING", "VISION"]
            for key in bool_vars:
                pattern = re.compile(rf"^{key}\s*=\s*(True|False)", re.MULTILINE)
                match = pattern.search(content)
                if match:
                    config_data[key] = match.group(1) == "True"
                else:
                    config_data[key] = False # Default

            return config_data

        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def save_config(self, new_data: dict):
        """
        Updates the config file with new values.
        Uses regex replacement to preserve comments and structure.
        """
        if not self.config_path.exists():
            return False

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                content = f.read()

            # String Variables
            str_vars = ["PERSONA", "BACKEND", "LOCAL_MODEL", "AI_MODEL"]
            for key in str_vars:
                if key in new_data:
                    new_val = new_data[key]
                    # Regex to find the line and substitute
                    # We only replace the quoted part to keep comments if they exist after?
                    # Actually standard replacement of the whole 'KEY = "VAL"' part is safer.
                    # Pattern: ^KEY\s*=\s*['"].*?['"]
                    # Limit to start of line to avoid partial matches
                    pattern = re.compile(rf"^{key}\s*=\s*(['\"].*?['\"])", re.MULTILINE)
                    # Replacement: KEY = "new_val"
                    # We try to detect the original quote style? Hard. Let's force double quotes.
                    replacement = f'{key} = "{new_val}"'
                    content = pattern.sub(replacement, content)

            # Boolean Variables
            bool_vars = ["VOICE", "THINKING_SUPPORT", "FUNCTION_CALLING_SUPPORT", "OLLAMA_CLOUD",
                         "VERTEX", "PAST_MEMORY", "CONTEXT_CACHING", "VISION"]
            for key in bool_vars:
                if key in new_data:
                    new_val = str(new_data[key]) # "True" or "False"
                    pattern = re.compile(rf"^{key}\s*=\s*(True|False)", re.MULTILINE)
                    replacement = f'{key} = {new_val}'
                    content = pattern.sub(replacement, content)

            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return True

        except Exception as e:
            print(f"Error saving config: {e}")
            return False
