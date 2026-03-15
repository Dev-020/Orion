import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .fivetools_loader import loader
from backends.main_utils import config

logger = logging.getLogger(__name__)

def search(
    query: Optional[str] = None,
    item_type: Optional[str] = None,
    source: Optional[str] = None,
    mode: str = 'summary',
    max_results: int = 25
) -> List[Dict[str, Any]]:
    """
    Searches across cached 5eTools collections.
    """
    results = []
    
    # Identify which collections to search
    collections_to_search = []
    if item_type:
        collections_to_search = [item_type]
    else:
        # Search all mapped collections
        collections_to_search = list(loader.collections_map.keys())

    for col_name in collections_to_search:
        collection = loader.get_collection(col_name)
        for item in collection:
            # Filter by query (name substring)
            if query and query.lower() not in item.get("name", "").lower():
                continue
            
            # Filter by source
            if source and source.upper() != item.get("source", "").upper():
                continue
            
            results.append(item)
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    if mode == 'summary':
        return [
            {"id": item["id"], "name": item["name"], "type": item["type"], "source": item["source"]}
            for item in results
        ]
    
    return results

def get_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single full item by its generated ID."""
    # The ID prefix usually indicates the collection
    parts = item_id.split("_")
    if not parts:
        return None
    
    # Try to guess collection from prefix
    possible_col = parts[0]
    if possible_col in loader.collections_map:
        collection = loader.get_collection(possible_col)
        for item in collection:
            if item["id"] == item_id:
                return item
    
    # Fallback: search all collections (rarely needed if IDs are unique and prefixed)
    for col_name in loader.collections_map:
        if col_name == possible_col:
            continue
        collection = loader.get_collection(col_name)
        for item in collection:
            if item["id"] == item_id:
                return item
                
    return None

def list_searchable_types() -> Dict[str, Any]:
    """
    Discovers searchable types and source codes by scanning the 5eTools schema directory.
    Returns a dictionary with 'item_types' and 'sources'.
    """
    schema_dir = config.FIVETOOLS_SCHEMA_DIR
    types_found = {}
    sources_found = {}
    
    if not schema_dir.exists():
        logger.warning(f"Schema directory {schema_dir} not found.")
        return {"item_types": {}, "sources": {}}

    # 1. Discover item_types from schema files
    # Scan .json files in the schema directory and subdirectories
    schema_files = list(schema_dir.glob("*.json")) + list(schema_dir.glob("*/*.json"))
    
    skip_files = [
        "index.json", "util.json", "homebrew.json", "entry.json", "util-", "foundry-", 
        "fluff-", "makebrew-", "makecards-", "renderdemo-", "sources-", "corpus-", 
        "converter.json", "citations.json", "changelog.json", "encounterbuilder.json"
    ]
    
    for schema_file in schema_files:
        if any(skip in schema_file.name for skip in skip_files):
            continue
            
        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)
                title = schema_data.get("title", schema_file.stem.capitalize())
                
                # Normalize type name: 'spells' -> 'spell', 'bestiary' -> 'bestiary'
                stem = schema_file.stem.lower()
                base_type = stem
                if base_type.endswith("s") and base_type not in ["class", "bastions", "bastion", "objects", "object", "senses", "skills"]:
                    base_type = base_type[:-1]
                
                # Map some specific 5eTools names to Orion's expected types
                type_map = {
                    "bestiary": "bestiary", # monster is already normalized from stem 'bestiary' -> 'bestiary'? Wait, stem is 'bestiary'.
                }
                base_type = type_map.get(base_type, base_type)
                
                types_found[base_type] = title
        except Exception as e:
            logger.error(f"Error parsing schema {schema_file}: {e}")

    # 2. Discover source codes from sources-5etools.json
    sources_file = schema_dir / "sources-5etools.json"
    if sources_file.exists():
        try:
            with open(sources_file, 'r', encoding='utf-8') as f:
                sources_data = json.load(f)
                # In 5eTools, sources are usually under a specific key in the schema or just an enum
                # This schema defines the structure of source objects
                # For discovery, it's easier to look at the 'data' if we had a full source list.
                # But sources-5etools.json usually contains the metadata about sources.
                pass 
        except Exception as e:
            logger.error(f"Error parsing sources schema: {e}")

    # Fallback/Manual additions for common sources
    common_sources = {
        "PHB": "Player's Handbook",
        "MM": "Monster Manual",
        "DMG": "Dungeon Master's Guide",
        "XGE": "Xanathar's Guide to Everything",
        "TCE": "Tasha's Cauldron of Everything",
        "MPMM": "Mordenkainen Presents: Monsters of the Multiverse",
        "VGM": "Volo's Guide to Monsters",
        "SCAG": "Sword Coast Adventurer's Guide",
        "ERLW": "Eberron: Rising from the Last War",
        "FTD": "Fizban's Treasury of Dragons"
    }
    for code, name in common_sources.items():
        if code not in sources_found:
            sources_found[code] = name

    # Ensure mapped collections in loader are included
    for col in loader.collections_map:
        if col not in types_found:
            types_found[col] = col.capitalize()

    return {
        "item_types": types_found,
        "sources": sources_found
    }
