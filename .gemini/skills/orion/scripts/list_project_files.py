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
    subdirectory = os.environ.get("SUBDIRECTORY", ".")
    
    try:
        persona = os.environ.get("ORION_PERSONA", "default")
        functions.initialize_persona(persona)
        
        result = functions.list_project_files(subdirectory=subdirectory)
        print(result)
    except Exception as e:
        print(f"Error executing list_project_files: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
