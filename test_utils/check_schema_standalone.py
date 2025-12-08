import sqlite3
import os
from pathlib import Path

def check_schema():
    # Hardcode path logic to avoid import issues
    PROJECT_ROOT = Path("c:/GitBash/Orion")
    persona = "default"
    db_path = PROJECT_ROOT / 'databases' / persona / 'orion_database.sqlite'
    
    print(f"Checking schema for: {db_path}")
    
    if not db_path.exists():
         print("DB File not found.")
         return

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(deep_memory)")
            columns = cursor.fetchall()
            
            if not columns:
                print("Table 'deep_memory' not found!")
                return

            print("Columns in 'deep_memory':")
            for col in columns:
                print(f"  - {col[1]} ({col[2]})")

    except Exception as e:
        print(f"Error reading schema: {e}")

if __name__ == "__main__":
    check_schema()
