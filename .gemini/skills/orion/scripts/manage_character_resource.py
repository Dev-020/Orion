#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Identify project root (Skill is 4 levels deep: .gemini/skills/orion/scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backends"
sys.path.insert(0, str(BACKEND_DIR))

from main_utils import dnd_functions

def main():
    # Gemini CLI maps tool parameters to env vars (UPPERCASE)
    user_id = os.environ.get("USER_ID")
    operation = os.environ.get("OPERATION")
    resource_name = os.environ.get("RESOURCE_NAME")
    value_str = os.environ.get("VALUE")
    max_value_str = os.environ.get("MAX_VALUE")
    
    if not user_id or not operation:
        print("Error: 'user_id' and 'operation' parameters are required.")
        sys.exit(1)
        
    try:
        value = int(value_str) if value_str and value_str.lower() != "none" else None
        max_value = int(max_value_str) if max_value_str and max_value_str.lower() != "none" else None
        
        result = dnd_functions.manage_character_resource(
            user_id=user_id,
            operation=operation,
            resource_name=resource_name,
            value=value,
            max_value=max_value
        )
        print(result)
    except Exception as e:
        print(f"Error executing manage_character_resource: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
