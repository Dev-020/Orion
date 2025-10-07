
import json
import os
from collections import defaultdict

# Define the paths relative to the script's location
# Assumes the script is in misc_scripts/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_FILE_PATH = os.path.join(BASE_DIR, "old_files", "_knowledge_base_ARCHIVE", "knowledge_base_schema.json")
OUTPUT_FILE_PATH = os.path.join(BASE_DIR, "instructions", "deep_schema_analysis.json") # Changed output file name

def _get_value_type(value):
    """Determines the simple type of a value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int) or isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return "unknown"

def _traverse_schema(schema, path_counts, current_path=""):
    """
    Recursively traverses the schema to find all metadata paths, their counts, and types.
    """
    if isinstance(schema, dict):
        for key, value in schema.items():
            new_path = f"{current_path}.{key}" if current_path else key
            _traverse_schema(value, path_counts, new_path)
    elif isinstance(schema, list):
        # Represent lists with [*] and analyze the first element if it exists
        new_path = f"{current_path}[*]"
        if schema:
            _traverse_schema(schema[0], path_counts, new_path)
    else:
        # This is a leaf node (a value)
        path_info = path_counts[current_path]
        path_info["count"] += 1
        # Store the type of the value
        path_info["type"] = _get_value_type(schema)


def analyze_schema():
    """
    Analyzes the per-file schema to count the occurrences of each full metadata path,
    grouped by the folder it belongs to.
    """
    print(f"Loading schema from: {SCHEMA_FILE_PATH}")
    try:
        with open(SCHEMA_FILE_PATH, 'r', encoding='utf-8') as f:
            per_file_schema = json.load(f)
        print("Schema loaded successfully.")
    except FileNotFoundError:
        print(f"ERROR: Schema file not found at {SCHEMA_FILE_PATH}")
        return
    except json.JSONDecodeError:
        print(f"ERROR: Could not decode JSON from {SCHEMA_FILE_PATH}")
        return

    # e.g., {"spells": {"level": {"count": 500, "type": "number"}, ...}, "bestiary": ...}
    folder_analysis = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    print(f"Analyzing {len(per_file_schema)} file schemas...")

    for file_path, file_schema in per_file_schema.items():
        try:
            # Path is like "knowledge_base/spells/spell-name.json"
            parts = file_path.replace("\\", "/").split('/')
            if len(parts) > 1:
                folder_name = parts[1]
            else:
                continue

            # If the folder is 'generated', skip it to avoid metadata bloat
            if folder_name == "generated":
                continue

            # Recursively traverse the schema for the current file
            _traverse_schema(file_schema, folder_analysis[folder_name])

        except Exception as e:
            print(f"Could not process path {file_path}: {e}")
            continue
    
    print("Analysis complete.")

    # Convert defaultdicts to regular dicts and sort them by count
    final_output = {}
    sorted_folders = sorted(folder_analysis.keys())

    for folder in sorted_folders:
        # Sort the keys within each folder by their count, descending
        # Accessing the count from the nested dictionary for sorting
        sorted_keys = sorted(folder_analysis[folder].items(), key=lambda item: item[1]["count"], reverse=True)
        final_output[folder] = dict(sorted_keys)

    print(f"Saving deep, grouped, and sorted analysis to: {OUTPUT_FILE_PATH}")
    try:
        with open(OUTPUT_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, indent=2)
        print("Successfully saved the deep schema analysis.")
    except IOError as e:
        print(f"ERROR: Could not write to output file {OUTPUT_FILE_PATH}: {e}")

if __name__ == "__main__":
    analyze_schema()
