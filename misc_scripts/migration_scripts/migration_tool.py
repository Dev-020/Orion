# migration_tool.py
import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any

def migrate_knowledge_base():
    """
    Parses the old, folder-based knowledge base and migrates it to a single,
    unified JSON database with a standardized schema.
    This script is designed to be run only once.
    """
    print("--- Starting Knowledge Base Migration ---")

    # --- 1. Setup Paths ---
    # Establishes the core directories we'll be working with.
    # It assumes the script is run from the project's root directory.
    base_dir = Path(__file__).parent.resolve()
    kb_path = base_dir / 'knowledge_base'
    output_file = kb_path / 'unified_database.json'
    
    # Safety check to ensure the knowledge base directory actually exists.
    if not kb_path.is_dir():
        print(f"FATAL ERROR: Knowledge base directory not found at '{kb_path}'")
        return

    # --- 2. Initialize ---
    # This list will store all the final, structured entries before we write them to the new file.
    unified_data: List[Dict[str, Any]] = []
    processed_files_count = 0
    migrated_entries_count = 0

    print(f"Scanning directory: {kb_path}")
    print(f"Output will be written to: {output_file}\n")

    # --- 3. Walk the Directory Structure ---
    # We use os.walk to go through each folder (adventure, bestiary, etc.) and each file within it.
    for root, _, files in os.walk(kb_path):
        # The 'category' is the name of the folder the file is in (e.g., "spells", "bestiary").
        # This will become the "type" in our new schema.
        category = Path(root).name

        for filename in files:
            # We only care about .json files. We also specifically ignore the output file itself
            # in case the script is run more than once.
            if filename.endswith('.json') and filename != 'unified_database.json':
                filepath = Path(root) / filename
                print(f"-> Processing '{category}/{filename}'...")

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                    
                    # --- 4. Extract the Main Data List ---
                    # Based on our schema analysis, data is either a direct list `[]`
                    # or nested inside a dictionary `{"key": []}`. This handles both cases.
                    item_list = []
                    if isinstance(content, list):
                        item_list = content
                    elif isinstance(content, dict):
                        # Find the first key that holds a list of objects, ignoring metadata keys.
                        data_key = next((k for k, v in content.items() if isinstance(v, list) and not k.startswith('__')), None)
                        if data_key:
                            item_list = content[data_key]
                        else:
                            # This handles files that are just a single object, like index.json
                            # We will treat the whole file as one item.
                            item_list = [content]
                    
                    if not item_list:
                        print(f"  - SKIPPED: No list of items found in file.")
                        continue

                    # --- 5. Process Each Item in the File ---
                    for item in item_list:
                        # Ensure the item is a dictionary and has a 'name' key, which is our
                        # primary identifier for searching. If not, we can't process it.
                        if not isinstance(item, dict) or "name" not in item:
                            continue

                        # Create the new, structured object (the "labeled box").
                        new_entry = {
                            "id": str(uuid.uuid4()),
                            "type": category,
                            "name": item.get("name"),
                            "source": item.get("source"),
                            "data": item  # This is the "sealed box" - the complete, original object.
                        }
                        unified_data.append(new_entry)
                        migrated_entries_count += 1
                    
                    processed_files_count += 1

                except json.JSONDecodeError:
                    print(f"  - WARNING: Could not parse '{filename}'. It may be invalid JSON. Skipping.")
                except Exception as e:
                    print(f"  - ERROR: An unexpected error occurred with '{filename}': {e}. Skipping.")

    # --- 6. Write the Final Unified Database ---
    if unified_data:
        print(f"\n--- Migration Summary ---")
        print(f"Successfully processed {processed_files_count} files.")
        print(f"A total of {migrated_entries_count} entries have been migrated.")
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(unified_data, f, indent=2)
            print(f"\nSUCCESS: New unified database created at: '{output_file}'")
        except Exception as e:
            print(f"\nFATAL ERROR: Could not write to output file '{output_file}'. Reason: {e}")
    else:
        print("\n--- Migration Failed: No data was processed. The 'knowledge_base' directory might be empty or structured unexpectedly. ---")

if __name__ == "__main__":
    migrate_knowledge_base()