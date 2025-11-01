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
from main_utils import main_functions as functions

# --- CONFIGURATION ---
# Centralized paths for clarity and easy modification.
DB_FILE = PROJECT_ROOT / "databases" / "default" / "orion_database.sqlite"
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
    """Generates a machine-readable schema of all available tools from main_functions.py."""
    print("\nGenerating tool_schema.json...")
    schema = {}
    
    # Use the __all__ list from main_functions.py as the source of truth for public tools
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

# In generate_manifests.py, replace the existing function with this one.

def generate_db_schema_json(conn, output_dir):
    """
    Generates a rich db_schema.json file that includes both the table columns
    and the strategic configuration for Vector DB synchronization.
    """
    print("\nGenerating rich db_schema.json...")
    cursor = conn.cursor()
    
    # This is our manually curated "Schema Map" configuration.
    # It defines the sync strategy for each table that has a VDB counterpart.
    VDB_CONFIG = {
        'long_term_memory': {
            'primary_key': 'event_id',
            'text_column': 'description',
            'vdb_id_strategy': 'direct'  # The PK is already a stable UID.
        },
        'active_memory': {
            'primary_key': 'topic',
            'text_column': 'ruling',
            'vdb_id_strategy': 'generate' # The PK is a mutable string; generate a new UID for the VDB.
        },
        'deep_memory': {
            'primary_key': 'id',
            'text_column': 'response_text',
            'vdb_id_strategy': 'direct'  # The PK is a stable integer.
        },
        'instruction_proposals': {
            'primary_key': 'proposal_name',
            'text_column': 'diff_text',
            'vdb_id_strategy': 'generate'
        },
        'knowledge_base': {
            'primary_key': 'id',
            'text_column': 'data',
            'vdb_id_strategy': 'direct'
        },
        'knowledge_schema': {
            'primary_key': 'id',
            'text_column': 'path',
            'vdb_id_strategy': 'direct'
        },
        'user_profiles': {
            'primary_key': 'user_id',
            'text_column': 'notes',
            'vdb_id_strategy': 'direct'
        }
        # You can manually add other tables like 'knowledge_base' here as they are migrated.
    }

    schema = {}
    
    # Get the list of all tables in the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table['name']
        
        # Get the columns for the current table
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_info = cursor.fetchall()
        columns = [info['name'] for info in columns_info]
        
        # --- THIS IS THE FIX ---
        # 1. Always start with a dictionary.
        table_data: dict[str, Any] = {
            'columns': columns
        }
        
        # 2. If the table has a VDB config, merge it into the dictionary.
        if table_name in VDB_CONFIG:
            table_data.update(VDB_CONFIG[table_name])
        
        # 3. Assign the final dictionary to the schema.
        schema[table_name] = table_data
        # --- END OF FIX ---
            
    # Use the existing helper to write the final, rich schema file
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
    """
    Main function to run the entire manifest generation process.
    Each generator is wrapped in a try/except block to make the process resilient.
    """
    # Ensure the output directory exists.
    OUTPUT_DIR.mkdir(exist_ok=True)

    # --- Manifest Generation ---
    # The process is designed to be resilient. If one manifest fails, the script
    # prints a warning and moves on to the next, ensuring that as many manifests
    # as possible are generated.

    # Attempt to generate manifests that do not require a database connection first.
    try:
        generate_tool_schema_json(OUTPUT_DIR)
    except Exception as e:
        print(f"  -> WARNING: Failed to generate tool_schema.json. Skipping. Reason: {e}")

    # Establish database connection
    conn = get_db_connection(DB_FILE)
    if not conn:
        print("\nSkipping all DB-related manifests due to connection failure.")
        # Even if the DB fails, we should still attempt to create the master manifest.
        try:
            generate_master_manifest(OUTPUT_DIR)
        except Exception as e:
            print(f"  -> WARNING: Failed to generate master_manifest.json. Skipping. Reason: {e}")
        
        print("\n--- Manifest generation process finished. ---")
        return

    # Proceed with DB-dependent manifests
    try:
        # A list of database-dependent generator functions to iterate through.
        db_generators = [
            generate_user_profile_manifest,
            generate_long_term_memory_manifest,
            generate_active_memory_manifest,
            generate_pending_logs_json,
            generate_db_schema_json
        ]
        
        for generator_func in db_generators:
            try:
                # The function name (e.g., "generate_user_profile_manifest") is used for logging.
                generator_name = generator_func.__name__
                generator_func(conn, OUTPUT_DIR)
            except Exception as e:
                print(f"  -> WARNING: Failed to run {generator_name}. Skipping. Reason: {e}")

    finally:
        # --- Finalization ---
        # Always close the connection and generate the master list of manifests.
        if conn:
            conn.close()
            print("\nDatabase connection closed.")
        
        # The master manifest should always be generated last.
        try:
            generate_master_manifest(OUTPUT_DIR)
        except Exception as e:
            print(f"  -> WARNING: Failed to generate master_manifest.json. Skipping. Reason: {e}")
            
        print("\n--- Manifest generation process finished. ---")

if __name__ == "__main__":
    main()