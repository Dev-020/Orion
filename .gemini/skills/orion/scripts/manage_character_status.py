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
    effect_name = os.environ.get("EFFECT_NAME")
    details = os.environ.get("DETAILS")
    duration_str = os.environ.get("DURATION")
    
    if not user_id or not operation:
        print("Error: 'user_id' and 'operation' parameters are required.")
        sys.exit(1)
        
    try:
        duration = int(duration_str) if duration_str and duration_str.lower() != "none" else None
        
        result = dnd_functions.manage_character_status(
            user_id=user_id,
            operation=operation,
            effect_name=effect_name,
            details=details,
            duration=duration
        )
        print(result)
    except Exception as e:
        print(f"Error executing manage_character_status: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
