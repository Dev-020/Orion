import json
import tempfile
import os
import sys
from dotenv import load_dotenv

# Add the project root directory to the Python path to allow for module imports
# from the parent directory (e.g., 'functions.py').
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import functions

def export_latest_vdb_context_to_file():
    """
    Retrieves the latest vdb_context from the deep_memory table
    and writes it to a new temporary file.
    """
    print("--- [EXPORT] Retrieving latest vdb_context from deep_memory ---")
    
    query = "SELECT vdb_context FROM deep_memory ORDER BY id DESC LIMIT 1;"

    try:
        # Use the existing tool which handles connection and decompression
        # result_json = functions.execute_sql_read(query=query)
        # --- DB REPAIR LOGIC ---
        # This script is being used to repair the database by setting event_ids for NULL entries.
        load_dotenv()
        owner_id = os.getenv("DISCORD_OWNER_ID")
        if owner_id:
            functions.execute_sql_ddl(
                query="""
                    BEGIN TRANSACTION;
                    CREATE TABLE long_term_memory_new (event_id TEXT PRIMARY KEY NOT NULL, date TEXT NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL, snippet TEXT NOT NULL);
                    INSERT INTO long_term_memory_new SELECT event_id, date, title, category, description, snippet FROM long_term_memory;
                    DROP TABLE long_term_memory;
                    ALTER TABLE long_term_memory_new RENAME TO long_term_memory;
                    COMMIT;
                """,
                user_id=owner_id
            )


        #result_data = json.loads(result_json)
        result_data = None
        if result_data:
            latest_vdb_context = result_data[0].get('vdb_context')

            if latest_vdb_context:
                # Create a temporary file to write the content to.
                # 'delete=False' ensures the file is not deleted when the script ends.
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8', prefix='vdb_context_') as temp_file:
                    temp_file.write(latest_vdb_context)
                    temp_file_path = temp_file.name
                
                print(f"\n[SUCCESS] Successfully wrote vdb_context (length: {len(latest_vdb_context)} chars) to temporary file:")
                print(f"-> {os.path.abspath(temp_file_path)}")
            else:
                print("[INFO] The latest entry exists but has no vdb_context.")
        else:
            print("[INFO] No records found in the deep_memory table.")

    except json.JSONDecodeError:
        print(f"[ERROR] Failed to parse JSON from the database response: {result_json}")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")

if __name__ == "__main__":
    export_latest_vdb_context_to_file()