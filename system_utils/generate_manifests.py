# generate_manifests.py
import sqlite3
import json
import sys
from pathlib import Path
from typing import Any
import inspect
import os

# --- ROBUST PATHING & IMPORT FIX ---
# 1. Determine the project root directory (which is the parent of 'system_utils')
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 2. Add the project root to the system path to allow for absolute imports
sys.path.insert(0, str(PROJECT_ROOT))

# --- DYNAMICALLY IMPORT THE TOOLS ---
# This is crucial for the tool schema generation.
import functions

# --- CONFIGURATION ---
# Centralized paths for clarity and easy modification.
DB_FILE = PROJECT_ROOT / "orion_database.sqlite"
OUTPUT_DIR = PROJECT_ROOT / "instructions"

def get_db_connection(db_file_path):
    """Establishes and returns a read-only connection to the SQLite database."""
    try:
        # URI=True allows us to specify read-only mode, which is safer for a read-only script.
        db_uri = f"file:{db_file_path}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row # Makes rows accessible by column name.
        print(f"Successfully connected to database '{db_file_path}' in read-only mode.")
        return conn
    except sqlite3.Error as e:
        print(f"FATAL: Database connection failed: {e}")
        print("Ensure the database file exists and the path is correct.")
        return None

def write_json_file(filepath: Path, data: Any):
    """A helper function to write data to a JSON file with pretty printing."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"  -> SUCCESS: Wrote {filepath.name}")
    except Exception as e:
        print(f"  -> ERROR: Failed to write {filepath.name}. Reason: {e}")

# --- NEW SCHEMA GENERATORS ---

def generate_tool_schema_json(output_dir):
    """Generates a machine-readable schema of all available tools from functions.py."""
    print("\nGenerating tool_schema.json...")
    schema = {}
    
    # Use the __all__ list from functions.py as the source of truth for public tools
    for func_name in functions.__all__:
        func = getattr(functions, func_name)
        try:
            sig = inspect.signature(func)
            parameters_schema = []
            for param in sig.parameters.values():
                param_info = {
                    "name": param.name,
                    "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any",
                    "required": param.default == inspect.Parameter.empty,
                }
                if not param_info["required"]:
                    param_info["default"] = param.default
                
                parameters_schema.append(param_info)

            schema[func_name] = {
                "description": inspect.getdoc(func),
                "parameters": parameters_schema
            }
        except (ValueError, TypeError) as e:
            print(f"  -> WARNING: Could not inspect function '{func_name}'. Skipping. Reason: {e}")

    write_json_file(output_dir / "tool_schema.json", schema)

def generate_db_schema_json(conn, output_dir):
    """Generates a manifest of the full database schema (tables and columns)."""
    print("\nGenerating db_schema.json...")
    schema = {}
    cursor = conn.cursor()
    
    # Get all table names, excluding sqlite system tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row['name'] for row in cursor.fetchall()]
    
    # Get columns for each table
    for table_name in tables:
        cursor.execute(f"PRAGMA table_info('{table_name}');")
        columns = [row['name'] for row in cursor.fetchall()]
        schema[table_name] = columns
        
    write_json_file(output_dir / "db_schema.json", schema)

# --- EXISTING MANIFEST GENERATORS ---

def generate_knowledge_base_manifest(conn, output_dir):
    """Generates a manifest of all items in the knowledge base."""
    print("\nGenerating knowledge_base_manifest.json...")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, type, source FROM knowledge_base ORDER BY name, source")
    rows = cursor.fetchall()
    
    manifest = [dict(row) for row in rows]
    
    write_json_file(output_dir / "knowledge_base_manifest.json", manifest)

def generate_user_profile_manifest(conn, output_dir):
    """Generates a manifest of all known users."""
    print("\nGenerating user_profile_manifest.json...")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, user_name FROM user_profiles ORDER BY user_name")
    rows = cursor.fetchall()
    
    # Structure the manifest as {"known_users": {id: name, ...}}
    manifest = {"known_users": {row['user_id']: row['user_name'] for row in rows}}
    
    write_json_file(output_dir / "user_profile_manifest.json", manifest)

def generate_long_term_memory_manifest(conn, output_dir):
    """Generates a manifest of all long-term memory titles."""
    print("\nGenerating long_term_memory_manifest.json...")
    cursor = conn.cursor()
    # We only need the ID and title for the manifest.
    cursor.execute("SELECT event_id, title FROM long_term_memory ORDER BY date DESC")
    rows = cursor.fetchall()
    
    manifest = [dict(row) for row in rows]
    
    write_json_file(output_dir / "long_term_memory_manifest.json", manifest)

def generate_active_memory_manifest(conn, output_dir):
    """Generates a lightweight manifest of active memory topics."""
    print("\nGenerating active_memory_manifest.json...")
    cursor = conn.cursor()
    cursor.execute("SELECT topic FROM active_memory ORDER BY topic")
    rows = cursor.fetchall()
    
    # Create a simple list of topic strings.
    manifest = [row['topic'] for row in rows]
    
    write_json_file(output_dir / "active_memory_manifest.json", manifest)

def generate_pending_logs_json(conn, output_dir):
    """Generates a full JSON dump of the pending_logs table."""
    print("\nGenerating pending_logs.json...")
    cursor = conn.cursor()
    cursor.execute("SELECT event_id, date, title, category, description, snippet FROM pending_logs")
    rows = cursor.fetchall()
    
    # Recreate the original list of dictionaries structure.
    data_list = []
    for row in rows:
        item = dict(row)
        # The 'category' field is stored as a JSON string, so we parse it back.
        try:
            item['category'] = json.loads(item['category'])
        except (json.JSONDecodeError, TypeError):
            # If category is not a valid JSON string, keep it as is.
            pass
        data_list.append(item)
        
    write_json_file(output_dir / "pending_logs.json", data_list)

# Add this function alongside the other generate_... functions in your script.
# It is designed to use the existing 'write_json_file' helper function.

def generate_master_manifest(output_dir: Path):
    """
    Scans the instructions directory and creates a master list of all
    non-text manifest and schema files.
    """
    print("\nGenerating master_manifest.json...")
    
    try:
        # Get all files in the directory
        all_files = os.listdir(output_dir)
        
        # Filter the list to exclude any file ending in .txt
        # and also exclude the master manifest itself to prevent recursion.
        filtered_files = [
            f for f in all_files 
            if not f.endswith('.txt') and f != 'master_manifest.json'
        ]
        
        # Use the existing helper function to write the file
        write_json_file(output_dir / "master_manifest.json", filtered_files)
        
    except Exception as e:
        print(f"  -> ERROR: Failed to generate master_manifest.json: {e}")

def main():
    """Main function to run the entire manifest generation process."""
    # Ensure the output directory exists.
    OUTPUT_DIR.mkdir(exist_ok=True)

    # --- Generate New Schemas FIRST ---
    # Tool schema does not require a DB connection.
    generate_tool_schema_json(OUTPUT_DIR)

    conn = get_db_connection(DB_FILE)
    if not conn:
        return

    try:
        # DB schema and other manifests require a DB connection.
        generate_db_schema_json(conn, OUTPUT_DIR)
        
        # --- Generate Existing Manifests ---
        generate_user_profile_manifest(conn, OUTPUT_DIR)
        generate_long_term_memory_manifest(conn, OUTPUT_DIR)
        generate_active_memory_manifest(conn, OUTPUT_DIR)
        generate_pending_logs_json(conn, OUTPUT_DIR)
        generate_db_schema_json(conn, OUTPUT_DIR)
        generate_tool_schema_json(OUTPUT_DIR)
        generate_master_manifest(OUTPUT_DIR)
    finally:
        conn.close()
        print("\n--- Manifest generation complete. ---")

if __name__ == "__main__":
    main()
