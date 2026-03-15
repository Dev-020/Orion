import sqlite3
import json
from pathlib import Path

def check_db(db_path):
    print(f"--- Checking: {db_path} ---")
    if not db_path.exists():
        print("File not found.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables: {tables}")
    
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        cols = [row[1] for row in cursor.fetchall()]
        print(f"  {table}: {cols}")
    conn.close()

check_db(Path("databases/default/orion_database.sqlite"))
check_db(Path("databases/dnd/orion_database.sqlite"))
