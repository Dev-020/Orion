#!/usr/bin/env python3
import os
import sys
import io
import time
from pathlib import Path
from types import SimpleNamespace

# Identify project root (Skill is 4 levels deep)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backends"
sys.path.insert(0, str(BACKEND_DIR))

from main_utils import config, main_functions as functions
from google.genai import Client, types

class MockCore:
    def __init__(self):
        self.backend = "api"
        self.client = Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.current_turn_context = {}
        # Minimal file_manager mock for main_functions compatibility
        self.file_manager = SimpleNamespace(
            process_file=self.upload_file
        )

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """Standard upload logic for Gemini API."""
        try:
            file_handle = self.client.files.upload(
                file=io.BytesIO(file_bytes),
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=display_name
                )
            )
            while file_handle.state.name == "PROCESSING":
                time.sleep(1)
                file_handle = self.client.files.get(name=file_handle.name)
            return file_handle
        except Exception as e:
            print(f"Upload Error: {e}")
            return None

def main():
    file_path = os.environ.get("FILE_PATH")
    start_line_raw = os.environ.get("START_LINE")
    end_line_raw = os.environ.get("END_LINE")
    
    if not file_path:
        print("Error: 'file_path' parameter is required.")
        sys.exit(1)
        
    try:
        start_line = int(start_line_raw) if start_line_raw and str(start_line_raw).isdigit() else None
        end_line = int(end_line_raw) if end_line_raw and str(end_line_raw).isdigit() else None
        
        # Initialize Mock Core for multi-modal support
        config.ORION_CORE_INSTANCE = MockCore()
        functions.initialize_persona(os.environ.get("ORION_PERSONA", "default"))
        
        result = functions.read_file(file_path=file_path, start_line=start_line, end_line=end_line)
        print(result)
    except Exception as e:
        print(f"Error executing read_file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
