#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Identify project root (Skill is 4 levels deep)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backends"
sys.path.insert(0, str(BACKEND_DIR))

from main_utils import main_functions as functions

def main():
    url_raw = os.environ.get("URL")
    query = os.environ.get("QUERY")
    
    if not url_raw:
        print("Error: 'url' parameter is required.")
        sys.exit(1)
        
    try:
        url = json.loads(url_raw) if url_raw.startswith('[') else url_raw
        
        persona = os.environ.get("ORION_PERSONA", "default")
        functions.initialize_persona(persona)
        
        result = functions.browse_website(url=url, query=query)
        print(result)
    except Exception as e:
        print(f"Error executing browse_website: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
