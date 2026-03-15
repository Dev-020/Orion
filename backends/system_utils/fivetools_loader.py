import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from main_utils import config

logger = logging.getLogger(__name__)

class FiveToolsLoader:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.cache: Dict[str, List[Dict[str, Any]]] = {}
        
        # Mapping of collection names to file/directory paths and their JSON keys
        self.collections_map = {
            "spell": {"path": "spells", "key": "spell", "is_dir": True},
            "bestiary": {"path": "bestiary", "key": "monster", "is_dir": True},
            "item": {"path": "items.json", "key": "item", "is_dir": False},
            "feat": {"path": "feats.json", "key": "feat", "is_dir": False},
            "race": {"path": "races.json", "key": "race", "is_dir": False},
            "background": {"path": "backgrounds.json", "key": "background", "is_dir": False},
            "optionalfeature": {"path": "optionalfeatures.json", "key": "optionalfeature", "is_dir": False},
            "class": {"path": "class", "key": "class", "is_dir": True},
            "subclass": {"path": "class", "key": "subclass", "is_dir": True},
            "adventure": {"path": "adventures.json", "key": "adventure", "is_dir": False},
            "book": {"path": "books.json", "key": "book", "is_dir": False},
        }

    def _normalize_item(self, item: Dict[str, Any], item_type: str) -> Dict[str, Any]:
        """Adds standard fields if missing and generates a unique ID."""
        name = item.get("name", "Unknown")
        source = item.get("source", "Unknown")
        # Generate slugified ID: type_name_source
        # Remove characters that might break things but keep it readable
        clean_name = "".join(c if c.isalnum() or c in " _-" else "" for c in name).strip()
        slug = f"{item_type}_{clean_name}_{source}".lower().replace(" ", "_").replace("-", "_")
        item["id"] = slug
        item["type"] = item_type
        return item

    def get_collection(self, collection_name: str) -> List[Dict[str, Any]]:
        """Loads and caches a collection if not already present."""
        if collection_name in self.cache:
            return self.cache[collection_name]

        if collection_name not in self.collections_map:
            logger.warning(f"Collection {collection_name} not mapped.")
            return []

        mapping = self.collections_map[collection_name]
        items = []
        path = self.data_dir / mapping["path"]

        if not path.exists():
            logger.error(f"Path {path} does not exist. 5eTools data might be missing.")
            return []

        if mapping["is_dir"]:
            # Load from directory (index.json + referenced files)
            index_path = path / "index.json"
            if index_path.exists():
                try:
                    with open(index_path, 'r', encoding='utf-8') as f:
                        index = json.load(f)
                    for source_file in index.values():
                        file_path = path / source_file
                        if file_path.exists():
                            items.extend(self._load_from_file(file_path, mapping["key"], collection_name))
                except Exception as e:
                    logger.error(f"Error reading index {index_path}: {e}")
            else:
                # Fallback: load all .json files in dir
                for file_path in path.glob("*.json"):
                    if file_path.name != "index.json":
                        items.extend(self._load_from_file(file_path, mapping["key"], collection_name))
        else:
            # Load from single file
            items.extend(self._load_from_file(path, mapping["key"], collection_name))

        self.cache[collection_name] = items
        logger.info(f"Loaded {len(items)} items into collection '{collection_name}'")
        return items

    def _load_from_file(self, file_path: Path, key: str, item_type: str) -> List[Dict[str, Any]]:
        """Helper to load items from a JSON file using a specific key."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                raw_items = data.get(key, [])
                if not isinstance(raw_items, list):
                    return []
                return [self._normalize_item(i, item_type) for i in raw_items]
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return []

# Singleton instance
loader = FiveToolsLoader(config.FIVETOOLS_DATA_DIR)
