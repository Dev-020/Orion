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
    query_texts_raw = os.environ.get("QUERY_TEXTS")
    n_results_raw = os.environ.get("N_RESULTS", "7")
    where_raw = os.environ.get("WHERE")
    ids_raw = os.environ.get("IDS")
    
    if not query_texts_raw:
        print("Error: 'query_texts' parameter is required.")
        sys.exit(1)
        
    try:
        query_texts = json.loads(query_texts_raw) if query_texts_raw.startswith('[') else [query_texts_raw]
        n_results = int(n_results_raw)
        where = json.loads(where_raw) if where_raw and where_raw.startswith('{') else None
        ids = json.loads(ids_raw) if ids_raw and ids_raw.startswith('[') else None
        
        persona = os.environ.get("ORION_PERSONA", "default")
        functions.initialize_persona(persona)
        
        result = functions.execute_vdb_read(query_texts=query_texts, n_results=n_results, where=where, ids=ids)
        print(result)
    except Exception as e:
        print(f"Error executing execute_vdb_read: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
