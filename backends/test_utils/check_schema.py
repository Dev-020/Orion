import sqlite3
import os
from main_utils import config, main_functions as functions

def check_schema():
    # Initialize persona paths (default) to get DB_FILE
    functions.initialize_persona("default")
    db_path = config.DB_FILE
    
    print(f"Checking schema for: {db_path}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # Get table info
            cursor.execute("PRAGMA table_info(deep_memory)")
            columns = cursor.fetchall()
            
            if not columns:
                print("Table 'deep_memory' not found!")
                return

            print("Columns in 'deep_memory':")
            for col in columns:
                # col structure: (cid, name, type, notnull, dflt_value, pk)
                print(f"  - {col[1]} ({col[2]})")

    except Exception as e:
        print(f"Error reading schema: {e}")

if __name__ == "__main__":
    check_schema()
