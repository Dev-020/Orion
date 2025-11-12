# migrate_all_to_sqlite.py
import sqlite3
import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

# --- CONFIGURATION ---
# Defines the names and locations of our source files and the new database.
DB_FILE = "orion_database.sqlite"
UNIFIED_KB_JSON = "knowledge_base/unified_database.json"
DEEP_MEMORY_DIR = "deep_memory"
USER_PROFILES_JSON = "memory/user_profiles.json"
LONG_TERM_MEMORY_JSON = "instructions/long_term_memory.json"
ACTIVE_MEMORY_JSON = "instructions/active_memory.json"
PENDING_LOGS_JSON = "instructions/pending_logs.json"

# --- DATABASE SCHEMA ---
# The final, approved schema for our unified database.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_base (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_name ON knowledge_base (name);
CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_base (type);

CREATE TABLE IF NOT EXISTS deep_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    prompt_text TEXT,
    response_text TEXT,
    attachments_metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_deep_memory_user_id ON deep_memory (user_id);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL,
    aliases TEXT,
    first_seen TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS long_term_memory (
    event_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    snippet TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ltm_title ON long_term_memory (title);

CREATE TABLE IF NOT EXISTS active_memory (
    topic TEXT PRIMARY KEY,
    prompt TEXT,
    ruling TEXT NOT NULL,
    status TEXT NOT NULL,
    last_modified TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_logs (
    event_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    snippet TEXT NOT NULL
);
"""

def get_db_connection(db_file_path):
    """Establishes and returns a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(db_file_path)
        print(f"Successfully connected to database '{db_file_path}'.")
        return conn
    except sqlite3.Error as e:
        print(f"FATAL: Database connection failed: {e}")
        return None

def setup_database(conn):
    """Creates the tables and indexes from our schema."""
    try:
        cursor = conn.cursor()
        cursor.executescript(SCHEMA_SQL)
        conn.commit()
        print("Database schema created successfully.")
    except sqlite3.Error as e:
        print(f"FATAL: Schema creation failed: {e}")
        conn.close()
        exit()

def migrate_knowledge_base(conn, base_path):
    """Migrates data from unified_database.json to the knowledge_base table."""
    print("\n--- Migrating Knowledge Base ---")
    cursor = conn.cursor()
    kb_file = base_path / UNIFIED_KB_JSON
    try:
        with open(kb_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        to_insert = [
            (
                item.get('id'),
                item.get('type'),
                item.get('name'),
                item.get('source'),
                json.dumps(item.get('data', {}))
            ) for item in data
        ]
        
        cursor.executemany("INSERT INTO knowledge_base (id, type, name, source, data) VALUES (?, ?, ?, ?, ?)", to_insert)
        conn.commit()
        print(f"SUCCESS: Migrated {cursor.rowcount} entries to 'knowledge_base' table.")
    except FileNotFoundError:
        print(f"WARNING: '{kb_file}' not found. Skipping knowledge base migration.")
    except Exception as e:
        print(f"ERROR migrating knowledge base: {e}")

def migrate_deep_memory(conn, base_path):
    """Migrates all user archives from the deep_memory folder."""
    print("\n--- Migrating Deep Memory ---")
    cursor = conn.cursor()
    total_migrated = 0
    deep_memory_path = base_path / DEEP_MEMORY_DIR

    if not deep_memory_path.is_dir():
        print(f"WARNING: Directory '{deep_memory_path}' not found. Skipping deep memory migration.")
        return

    for filepath in deep_memory_path.glob('*.json'):
        user_id = filepath.stem
        print(f"  -> Processing archive for user_id: {user_id}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                user_archive = json.load(f)
            
            to_insert = []
            for session in user_archive:
                session_id = session.get("session_end_timestamp")
                if not session_id:
                    continue

                ts_dt = datetime.fromisoformat(session_id.replace('Z', '+00:00'))
                ts_unix = int(ts_dt.timestamp())

                for pair in session.get("pairs", []):
                    prompt_data = pair.get("prompt", "")
                    user_name = user_id # Default
                    prompt_text = prompt_data

                    # **CORRECTED LOGIC**: Check if the prompt is a nested JSON string
                    try:
                        # Attempt to load the prompt string as a JSON object
                        nested_prompt = json.loads(prompt_data)
                        if isinstance(nested_prompt, dict):
                            user_name = nested_prompt.get("user_name", user_id)
                            prompt_text = nested_prompt.get("prompt", prompt_data)
                    except (json.JSONDecodeError, TypeError):
                        # If it fails, it's a plain string, so we use it directly
                        pass

                    to_insert.append((
                        session_id,
                        user_id,
                        user_name,
                        ts_unix,
                        prompt_text,
                        pair.get("response", ""),
                        json.dumps(pair.get("attachments", [])) # Corrected key from your example
                    ))
            
            if to_insert:
                cursor.executemany("INSERT INTO deep_memory (session_id, user_id, user_name, timestamp, prompt_text, response_text, attachments_metadata) VALUES (?, ?, ?, ?, ?, ?, ?)", to_insert)
                total_migrated += cursor.rowcount
                print(f"    - Migrated {cursor.rowcount} entries for user {user_id}.")

        except Exception as e:
            print(f"  - ERROR processing file '{filepath.name}': {e}")
    
    conn.commit()
    print(f"SUCCESS: Migrated a total of {total_migrated} entries to 'deep_memory' table.")

def migrate_user_profiles(conn, base_path):
    """Migrates user_profiles.json, correctly handling the dictionary structure."""
    print("\n--- Migrating User Profiles ---")
    cursor = conn.cursor()
    file_path = base_path / USER_PROFILES_JSON
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        to_insert = []
        # **CORRECTED LOGIC**: Iterate through the dictionary's keys and values
        for user_id, profile_data in data.items():
            to_insert.append((
                user_id,
                profile_data.get("user_name"),
                json.dumps(profile_data.get("aliases", [])),
                profile_data.get("first_seen"),
                json.dumps(profile_data.get("notes", []))
            ))
        
        cursor.executemany("INSERT INTO user_profiles (user_id, user_name, aliases, first_seen, notes) VALUES (?, ?, ?, ?, ?)", to_insert)
        conn.commit()
        print(f"SUCCESS: Migrated {cursor.rowcount} entries to 'user_profiles' table.")
    except FileNotFoundError:
        print(f"WARNING: '{file_path}' not found. Skipping user profiles migration.")
    except Exception as e:
        print(f"ERROR migrating user profiles: {e}")

def migrate_active_memory(conn, base_path):
    """Migrates active_memory.json, adding a timestamp for last_modified."""
    print("\n--- Migrating Active Memory ---")
    cursor = conn.cursor()
    file_path = base_path / ACTIVE_MEMORY_JSON
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        to_insert = []
        # **CORRECTED LOGIC**: Generate a timestamp for the new 'last_modified' column
        now_iso = datetime.now(timezone.utc).isoformat()
        for topic, memory_data in data.items():
            to_insert.append((
                topic,
                memory_data.get("prompt", ""),
                memory_data.get("ruling"),
                memory_data.get("status"),
                now_iso # Add the current timestamp
            ))
            
        cursor.executemany("INSERT INTO active_memory (topic, prompt, ruling, status, last_modified) VALUES (?, ?, ?, ?, ?)", to_insert)
        conn.commit()
        print(f"SUCCESS: Migrated {cursor.rowcount} entries to 'active_memory' table.")
    except FileNotFoundError:
        print(f"WARNING: '{file_path}' not found. Skipping active memory migration.")
    except Exception as e:
        print(f"ERROR migrating active memory: {e}")

def migrate_simple_list(conn, file_path, table_name):
    """
    A more robust generic function for JSON lists like long_term_memory and pending_logs.
    This version correctly handles fields that might contain lists or dictionaries.
    """
    print(f"\n--- Migrating {file_path} ---")
    cursor = conn.cursor()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data:
            print("  - File is empty. Nothing to migrate.")
            return
            
        # Get column names from the table schema
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        
        to_insert = []
        for item in data:
            row_values = []
            for col in columns:
                value = item.get(col)
                # **CORRECTED LOGIC**: If the value is a list or dict, serialize it to a JSON string.
                if isinstance(value, (list, dict)):
                    row_values.append(json.dumps(value))
                else:
                    row_values.append(value)
            to_insert.append(tuple(row_values))
            
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        
        cursor.executemany(sql, to_insert)
        conn.commit()
        print(f"SUCCESS: Migrated {cursor.rowcount} entries to '{table_name}' table.")

    except FileNotFoundError:
        print(f"WARNING: '{file_path}' not found. Skipping this migration.")
    except Exception as e:
        print(f"ERROR migrating '{file_path}': {e}")

def main():
    """Main function to run the entire migration process."""
    base_path = Path(__file__).parent.resolve()
    db_path = base_path / DB_FILE

    if db_path.exists():
        print(f"Database file '{db_path}' already exists.")
        overwrite = input("Do you want to delete it and start over? (yes/no): ").lower()
        if overwrite == 'yes':
            os.remove(db_path)
            print("Old database removed.")
        else:
            print("Migration aborted.")
            return

    conn = get_db_connection(db_path)
    if not conn:
        return

    try:
        setup_database(conn)
        migrate_knowledge_base(conn, base_path)
        migrate_deep_memory(conn, base_path)
        migrate_user_profiles(conn, base_path)
        migrate_active_memory(conn, base_path)
        migrate_simple_list(conn, base_path / LONG_TERM_MEMORY_JSON, "long_term_memory")
        migrate_simple_list(conn, base_path / PENDING_LOGS_JSON, "pending_logs")
    finally:
        conn.close()
        print("\n--- All migrations complete. ---")

if __name__ == "__main__":
    main()