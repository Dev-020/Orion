#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Identify project root (Skill is 4 levels deep: .gemini/skills/orion/scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backends"
sys.path.insert(0, str(BACKEND_DIR))

from main_utils import main_functions as functions

def main():
    # Gemini CLI maps tool parameters to env vars (UPPERCASE)
    query = os.environ.get("QUERY")
    params_json = os.environ.get("PARAMS", "[]")
    
    if not query:
        print("Error: 'query' parameter is required.")
        sys.exit(1)
        
    try:
        # Parse params if it's a JSON string, otherwise use it as is if it's already a list
        # Note: Gemini CLI often passes complex arguments as JSON strings in env vars.
        params = json.loads(params_json) if isinstance(params_json, str) and params_json.startswith('[') else params_json
        
        # Initialize persona if provided via env (optional)
        persona = os.environ.get("ORION_PERSONA", "default")
        functions.initialize_persona(persona)
        
        result = functions.execute_sql_read(query, params)
        print(result)
    except Exception as e:
        print(f"Error executing execute_sql_read: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
