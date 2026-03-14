#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Identify project root (Skill is 4 levels deep)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backends"
sys.path.insert(0, str(BACKEND_DIR))

from main_utils import config, main_functions as functions
from google.genai import Client

class MockCore:
    def __init__(self):
        self.backend = "api"
        self.client = Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.current_turn_context = {}

def main():
    task = os.environ.get("TASK")
    
    if not task:
        print("Error: 'task' parameter is required.")
        sys.exit(1)
        
    try:
        # Initialize Mock Core for agent delegation support
        config.ORION_CORE_INSTANCE = MockCore()
        functions.initialize_persona(os.environ.get("ORION_PERSONA", "default"))
        
        result = functions.delegate_to_native_tools_agent(task=task)
        print(result)
    except Exception as e:
        print(f"Error executing delegate_to_native_tools_agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
