import sqlite3
import json
import os

def refactor_knowledge_base():
    """
    Safely converts the 'data' column in the 'knowledge_base' table
    from TEXT to JSON for improved query performance by creating a new
    column, migrating data, and then replacing the old column.
    """
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'orion_database.sqlite'))
    print(f"Connecting to database at: {db_path}")

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # --- Check current schema ---
        cursor.execute("PRAGMA table_info(knowledge_base);")
        columns_info = {info[1]: info[2].upper() for info in cursor.fetchall()}

        if 'data' in columns_info and columns_info['data'] == 'JSON':
            print("Refactoring unnecessary. The 'data' column is already of type JSON.")
            return
        
        # --- Step 1: Add new 'metadata' column if it doesn't exist ---
        if 'metadata' not in columns_info:
            print("Step 1: Adding new 'metadata' column with JSON type...")
            cursor.execute("ALTER TABLE knowledge_base ADD COLUMN metadata JSON;")
            print("'metadata' column added successfully.")
        else:
            print("Step 1: 'metadata' column already exists, proceeding to migration.")

        # --- Step 2: Migrate data ---
        print("Step 2: Migrating data from 'data' (TEXT) to 'metadata' (JSON)...")
        cursor.execute("SELECT id, data FROM knowledge_base WHERE data IS NOT NULL AND metadata IS NULL;")
        rows = cursor.fetchall()

        if not rows:
            print("No new rows to migrate.")
        else:
            updated_count = 0
            for row_id, data_str in rows:
                try:
                    # Ensure the string is valid JSON
                    json_obj = json.loads(data_str)
                    # Use the json() function to insert as a proper JSON type
                    cursor.execute("UPDATE knowledge_base SET metadata = json(?) WHERE id = ?", (json.dumps(json_obj), row_id))
                    updated_count += 1
                except (json.JSONDecodeError, TypeError):
                    print(f"  - Warning: Could not parse data for id={row_id}. Skipping migration for this row.")
                    continue
            print(f"Successfully migrated data for {updated_count}/{len(rows)} rows.")
        
        conn.commit()

        # --- Step 3: Verify migrated data ---
        print("\nStep 3: Verifying data integrity...")
        cursor.execute("SELECT id, data, metadata FROM knowledge_base WHERE data IS NOT NULL;")
        verification_rows = cursor.fetchall()
        mismatch_found = False
        for row_id, data_str, metadata_json_str in verification_rows:
            try:
                original_obj = json.loads(data_str)
                migrated_obj = json.loads(metadata_json_str)
                if original_obj != migrated_obj:
                    print(f"  - FATAL: Data mismatch found for id={row_id}.")
                    mismatch_found = True
                    break
            except (json.JSONDecodeError, TypeError) as e:
                print(f"  - FATAL: Could not parse data for verification on id={row_id}. Error: {e}")
                mismatch_found = True
                break
        
        if mismatch_found:
            print("\nVerification failed. Aborting before any destructive changes.")
            conn.rollback()
        else:
            print("Verification successful. All data copied correctly.")
            
            # --- Step 4 & 5: Drop old column and rename new one ---
            print("\nStep 4: Dropping the old 'data' column...")
            cursor.execute("ALTER TABLE knowledge_base DROP COLUMN data;")
            print("Old 'data' column dropped.")
            
            print("Step 5: Renaming 'metadata' column to 'data'...")
            cursor.execute("ALTER TABLE knowledge_base RENAME COLUMN metadata TO data;")
            print("Column renamed successfully.")
            
            conn.commit()
            print("\nRefactoring complete. The 'data' column is now of type JSON.")

    except sqlite3.Error as e:
        print(f"\nAn error occurred: {e}")
        if conn:
            print("Rolling back changes...")
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    refactor_knowledge_base()
