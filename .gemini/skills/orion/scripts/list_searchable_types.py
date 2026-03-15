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
    try:
        result = dnd_functions.list_searchable_types()
        print(result)
    except Exception as e:
        print(f"Error executing list_searchable_types: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
