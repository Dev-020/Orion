#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Identify project root (Skill is 4 levels deep)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backends"
sys.path.insert(0, str(BACKEND_DIR))

from main_utils import main_functions as functions

def main():
    query = os.environ.get("QUERY")
    smart_filter_raw = os.environ.get("SMART_FILTER", "true")
    
    if not query:
        print("Error: 'query' parameter is required.")
        sys.exit(1)
        
    try:
        smart_filter = smart_filter_raw.lower() == "true"
        
        persona = os.environ.get("ORION_PERSONA", "default")
        functions.initialize_persona(persona)
        
        result = functions.search_web(query=query, smart_filter=smart_filter)
        print(result)
    except Exception as e:
        print(f"Error executing search_web: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
