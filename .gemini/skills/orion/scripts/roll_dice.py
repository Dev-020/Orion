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
    dice_notation = os.environ.get("DICE_NOTATION")
    
    if not dice_notation:
        print("Error: 'dice_notation' parameter is required.")
        sys.exit(1)
        
    try:
        result = dnd_functions.roll_dice(dice_notation)
        print(result)
    except Exception as e:
        print(f"Error executing roll_dice: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
