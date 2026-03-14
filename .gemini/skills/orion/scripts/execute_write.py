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
    table = os.environ.get("TABLE")
    operation = os.environ.get("OPERATION")
    user_id = os.environ.get("USER_ID")
    data_raw = os.environ.get("DATA")
    where_raw = os.environ.get("WHERE")
    
    if not (table and operation and user_id):
        print("Error: 'table', 'operation', and 'user_id' parameters are required.")
        sys.exit(1)
        
    try:
        data = json.loads(data_raw) if data_raw and (data_raw.startswith('{') or data_raw.startswith('[')) else None
        where = json.loads(where_raw) if where_raw and (where_raw.startswith('{') or where_raw.startswith('[')) else None
        
        persona = os.environ.get("ORION_PERSONA", "default")
        functions.initialize_persona(persona)
        
        result = functions.execute_write(table=table, operation=operation, user_id=user_id, data=data, where=where)
        print(result)
    except Exception as e:
        print(f"Error executing execute_write: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
