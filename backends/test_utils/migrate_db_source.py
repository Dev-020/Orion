import sqlite3
import os
from pathlib import Path

def migrate_schema():
    PROJECT_ROOT = Path("c:/GitBash/Orion")
    persona = "default"
    db_path = PROJECT_ROOT / 'databases' / persona / 'orion_database.sqlite'
    
    print(f"Migrating schema for: {db_path}")
    
    if not db_path.exists():
         print("DB File not found.")
         return

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if column exists first
            cursor.execute("PRAGMA table_info(deep_memory)")
            columns = [info[1] for info in cursor.fetchall()]
            
            if "model_source" in columns:
                print("Column 'model_source' already exists. Skipping.")
                return

            print("Adding column 'model_source'...")
            cursor.execute("ALTER TABLE deep_memory ADD COLUMN model_source TEXT DEFAULT 'gemini-3-pro-preview'")
            conn.commit()
            print("Migration successful.")

    except Exception as e:
        print(f"Error during migration: {e}")

if __name__ == "__main__":
    migrate_schema()
