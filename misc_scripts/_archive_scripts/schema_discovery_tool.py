# create_schema.py
import os
import json
import argparse
from copy import deepcopy
from pathlib import Path

def _merge_schemas(base_schema: any, new_schema: any) -> any:
    """Intelligently merges two schema structures together."""
    # (This function remains the same as schema_discovery_tool_v2.py)
    if type(base_schema) != type(new_schema):
        # If types are different, represent as a union string
        type_str_base = str(base_schema) if isinstance(base_schema, str) else type(base_schema).__name__
        type_str_new = str(new_schema) if isinstance(new_schema, str) else type(new_schema).__name__
        
        # Avoid creating redundant unions like "string | str"
        if type_str_base == "str": type_str_base = "string"
        if type_str_new == "str": type_str_new = "string"

        parts = set(type_str_base.split(" | "))
        parts.add(type_str_new)
        return " | ".join(sorted(list(parts)))

    if isinstance(base_schema, dict):
        merged = deepcopy(base_schema)
        for key, value in new_schema.items():
            if key not in merged:
                merged[key] = value
            else:
                merged[key] = _merge_schemas(merged[key], value)
        return merged
    elif isinstance(base_schema, list):
        if not new_schema: return base_schema
        if not base_schema: return new_schema
        return [_merge_schemas(base_schema[0], new_schema[0])]
    else:
        return base_schema

def _generate_structure_map(data: any) -> any:
    """Recursively generates a structure map for a given data object."""
    # (This function is modified slightly to call the new _merge_schemas)
    if isinstance(data, dict):
        return {key: _generate_structure_map(value) for key, value in data.items()}
    elif isinstance(data, list):
        if len(data) > 0:
            # Create a master schema for the list by merging all its elements
            master_list_schema = _generate_structure_map(data[0])
            for item in data[1:]:
                item_schema = _generate_structure_map(item)
                master_list_schema = _merge_schemas(master_list_schema, item_schema)
            return [master_list_schema]
        else:
            return []
    elif isinstance(data, (int, float)):
        return "number"
    elif isinstance(data, bool):
        return "boolean"
    else:
        return "string"

def create_schema_for_directory(input_dir: str, output_path: str):
    """
    Analyzes all JSON files in a directory and creates a unified schema map.
    
    Args:
        input_dir (str): The path to the directory to scan.
        output_path (str): The path where the final schema JSON will be saved.
    """
    print(f"--- Starting Schema Discovery for directory: '{input_dir}' ---")

    input_path = Path(input_dir)
    if not input_path.is_dir():
        print(f"FATAL ERROR: Input directory not found at '{input_dir}'")
        return

    master_schema = {}
    processed_files = 0

    for root, _, files in os.walk(input_path):
        for filename in files:
            if filename.endswith('.json'):
                filepath = Path(root) / filename
                relative_path = filepath.relative_to(input_path.parent).as_posix()
                print(f"Processing: {relative_path}")

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = json.load(f)

                    item_list = []
                    if isinstance(content, list):
                        item_list = content
                    elif isinstance(content, dict):
                        data_key = next((k for k, v in content.items() if isinstance(v, list) and not k.startswith('__')), None)
                        if data_key:
                            item_list = content[data_key]
                        else:
                            item_list = [content]

                    if not item_list:
                        master_schema[relative_path] = "empty_or_unrecognized_structure"
                        continue

                    file_master_schema = _generate_structure_map(item_list[0])
                    for item in item_list[1:]:
                        item_schema = _generate_structure_map(item)
                        file_master_schema = _merge_schemas(file_master_schema, item_schema)

                    master_schema[relative_path] = file_master_schema
                    processed_files += 1

                except json.JSONDecodeError:
                    print(f"  - WARNING: Could not parse '{filename}'. Invalid JSON.")
                    master_schema[relative_path] = "invalid_json"
                except Exception as e:
                    print(f"  - ERROR: An unexpected error occurred with '{filename}': {e}")
                    master_schema[relative_path] = f"error:_{e}"

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(master_schema, f, indent=2)
        print("\n--- Schema Discovery Complete! ---")
        print(f"Successfully analyzed and merged schemas from {processed_files} files.")
        print(f"Master schema map saved to: '{output_path}'")
    except Exception as e:
        print(f"\nFATAL ERROR: Could not write to output file '{output_path}'. Reason: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a structural schema from a directory of JSON files.")
    parser.add_argument("input_directory", help="The path to the directory containing JSON files to scan.")
    parser.add_argument("output_file", help="The path to save the output schema JSON file.")
    args = parser.parse_args()
    
    create_schema_for_directory(args.input_directory, args.output_file)