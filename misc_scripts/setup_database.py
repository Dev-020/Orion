import sqlite3
import os

# Correctly locate the project root directory (two levels up from the script)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(project_root, 'databases', 'default', 'orion_database.sqlite')

def create_tables():
    """
    Connects to the SQLite database and creates all necessary tables if they
    do not already exist. This script is intended to be run once for setup.
    """
    print(f"--- Initializing database at {DB_FILE} ---")
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            print("  - Creating 'deep_memory' table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deep_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    prompt_text TEXT,
                    response_text TEXT,
                    attachments_metadata TEXT, 
                    token INTEGER, 
                    function_calls JSON, 
                    vdb_context JSON
                )
            """)

            print("  - Creating 'user_profiles' table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT NOT NULL,
                    aliases TEXT,
                    first_seen TEXT NOT NULL,
                    notes TEXT
                )
            """)

            print("  - Creating 'restart_state' table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS restart_state (
                    session_id TEXT PRIMARY KEY,
                    history_blob BLOB NOT NULL, 
                    excluded_ids_blob BLOB
                )
            """)
            
            print("  - Creating 'long_term_memory' table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    event_id TEXT PRIMARY KEY NOT NULL, 
                    date TEXT NOT NULL, 
                    title TEXT NOT NULL, 
                    category TEXT NOT NULL, 
                    description TEXT NOT NULL, 
                    snippet TEXT NOT NULL
                )               
            """)

            print("  - Creating 'pending_logs' table...")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_logs (
                event_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                snippet TEXT NOT NULL
            )               
            """)
            # Add other table creation statements here as needed in the future
            # to keep all schema definitions in one place.

            conn.commit()
            print("--- Database tables created successfully. ---")

    except sqlite3.Error as e:
        print(f"---! DATABASE ERROR: {e} !---")

if __name__ == "__main__":
    # This allows the script to be run directly from the command line.
    # Example: python setup_database.py
    create_tables()