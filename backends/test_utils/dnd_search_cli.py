import sys
import json
import os
from pathlib import Path

# Add the backends directory to the Python path
project_root = Path(__file__).resolve().parent.parent.parent
backends_root = project_root / "backends"
sys.path.insert(0, str(backends_root))

# Hardcode D&D paths directly into the config BEFORE importing functions
from main_utils import config
config.DB_FILE = str(project_root / "databases" / "dnd" / "orion_database.sqlite")
config.CHROMA_DB_PATH = str(project_root / "databases" / "dnd" / "chroma_db_store")
config.COLLECTION_NAME = "orion_semantic_memory"
config.ENABLE_5ETOOLS_LOCAL = True

from main_utils import dnd_functions

def print_menu():
    print("\n" + "="*30)
    print("   ORION D&D SEARCH CLI")
    print("="*30)
    print("1. Search (Exact/Fuzzy Mode)")
    print("2. Search (Semantic/Conceptual Mode)")
    print("3. Get Full Entry (by ID)")
    print("4. List Searchable Types & Sources")
    print("5. Exit")

def main():
    print(f"Targeting D&D SQLite: {config.DB_FILE}")
    print(f"Targeting D&D Chroma: {config.CHROMA_DB_PATH}")

    while True:
        print_menu()
        choice = input("\nSelect an option: ")

        if choice == '1':
            query = input("Enter search query (name): ")
            item_type = input("Enter item type (e.g., spell, bestiary, feat) [Optional]: ")
            source = input("Enter source (e.g., PHB, XGE) [Optional]: ")
            
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
            semantic_query = input("Enter conceptual search (e.g., 'a spell that shoots frost'): ")
            item_type = input("Enter item type filter [Optional]: ")
            source = input("Enter source filter [Optional]: ")
            
            item_type = item_type.strip() if item_type.strip() else None
            source = source.strip() if source.strip() else None

            print(f"\nPerforming Semantic Search for '{semantic_query}'...")
            results_json = dnd_functions.search_knowledge_base(
                semantic_query=semantic_query,
                item_type=item_type,
                source=source,
                mode='summary'
            )
            print("\n--- Semantic Search Results ---")
            print(results_json)

        elif choice == '3':
            item_id = input("Enter exact Item ID: ")
            print(f"\nRetrieving full data for '{item_id}'...")
            result_json = dnd_functions.search_knowledge_base(id=item_id, mode='full')
            print("\n--- Full Entry Data ---")
            print(result_json)

        elif choice == '4':
            print("\nDiscovering searchable types and sources from schema...")
            types_json = dnd_functions.list_searchable_types()
            print("\n--- Available Types & Sources ---")
            print(types_json)

        elif choice == '5':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
