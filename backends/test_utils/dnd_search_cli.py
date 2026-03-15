import sys
import json
import os
from pathlib import Path

# Add project root to sys.path
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backends.main_utils import dnd_functions

def print_menu():
    print("\n" + "="*30)
    print("   ORION D&D SEARCH CLI")
    print("="*30)
    print("1. Search (Summary Mode)")
    print("2. Get Full Entry (by ID)")
    print("3. List Searchable Types & Sources")
    print("4. Exit")

def main():
    while True:
        print_menu()
        choice = input("\nSelect an option: ")

        if choice == '1':
            query = input("Enter search query (name): ")
            item_type = input("Enter item type (e.g., spell, bestiary, feat) [Optional]: ")
            source = input("Enter source (e.g., PHB, XGE) [Optional]: ")
            
            # Clean up optional inputs
            item_type = item_type.strip() if item_type.strip() else None
            source = source.strip() if source.strip() else None

            print(f"\nSearching for '{query}'...")
            results_json = dnd_functions.search_knowledge_base(
                query=query, 
                item_type=item_type, 
                source=source, 
                mode='summary'
            )
            print("\n--- Search Results ---")
            print(results_json)

        elif choice == '2':
            item_id = input("Enter exact Item ID: ")
            print(f"\nRetrieving full data for '{item_id}'...")
            result_json = dnd_functions.search_knowledge_base(id=item_id, mode='full')
            print("\n--- Full Entry Data ---")
            print(result_json)

        elif choice == '3':
            print("\nDiscovering searchable types and sources from schema...")
            types_json = dnd_functions.list_searchable_types()
            print("\n--- Available Types & Sources ---")
            print(types_json)

        elif choice == '4':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
