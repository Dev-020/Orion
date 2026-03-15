#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Identify project root (Skill is 4 levels deep: .gemini/skills/orion/scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backends"
sys.path.insert(0, str(BACKEND_DIR))

from main_utils import dnd_functions

def main():
    # Gemini CLI maps tool parameters to env vars (UPPERCASE)
    query = os.environ.get("QUERY")
    item_id = os.environ.get("ITEM_ID")
    item_type = os.environ.get("ITEM_TYPE")
    source = os.environ.get("SOURCE")
    semantic_query = os.environ.get("SEMANTIC_QUERY")
    mode = os.environ.get("MODE", "summary")
    max_results = int(os.environ.get("MAX_RESULTS", "25"))
    
    try:
        # Initialize DND paths if needed (The core already handles this, but for standalone skill calls we ensure it)
        # Note: In the Thin Wrapper, initialize_persona was already called by the core.
        
        result = dnd_functions.search_knowledge_base(
            query=query,
            id=item_id,
            item_type=item_type,
            source=source,
            semantic_query=semantic_query,
            mode=mode,
            max_results=max_results
        )
        print(result)
    except Exception as e:
        print(f"Error executing search_knowledge_base: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
