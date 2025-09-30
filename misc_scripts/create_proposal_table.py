import sqlite3
import os

# --- CONFIGURATION ---
DB_FILE = "orion_database.sqlite"
TABLE_NAME = "staged_proposals"

# The exact schema you provided. Using a multi-line string for readability.
TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS staged_proposals (
    proposal_name TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    new_content TEXT NOT NULL,
    diff_text TEXT NOT NULL,
    is_new_file INTEGER NOT NULL,
    timestamp TEXT NOT NULL
);
"""

def create_staged_proposals_table():
    """Connects to the database and creates the 'staged_proposals' table."""
    
    # Check if the database file exists in the current directory
    if not os.path.exists(DB_FILE):
        print(f"ERROR: Database file '{DB_FILE}' not found in the current directory.")
        print("Please run this script from the same folder as your database.")
        return

    conn = None  # Initialize conn to None
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        print(f"Successfully connected to '{DB_FILE}'.")
        
        # Execute the CREATE TABLE statement
        print(f"Attempting to create table '{TABLE_NAME}'...")
        cursor.execute(TABLE_SCHEMA)
        
        # Commit the changes
        conn.commit()
        
        print(f"Table '{TABLE_NAME}' created or already exists. Schema is ensured.")

    except sqlite3.Error as e:
        # This will catch errors, including "table already exists" if we remove "IF NOT EXISTS"
        print(f"An error occurred: {e}")
        
    finally:
        # Ensure the connection is closed, even if an error occurred
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    create_staged_proposals_table()