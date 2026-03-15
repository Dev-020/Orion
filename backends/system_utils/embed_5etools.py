import argparse
import hashlib
import json
import logging
import re
from pathlib import Path
import chromadb
import sys

# Add the backends directory to the Python path to resolve internal modules correctly
project_root = Path(__file__).resolve().parent.parent.parent
backends_root = project_root / "backends"
if str(backends_root) not in sys.path:
    sys.path.insert(0, str(backends_root))

from main_utils import config as cfg
from main_utils.orion_logger import setup_logging
from system_utils.fivetools_loader import loader

# --- CONFIGURATION ---
setup_logging("embed_5etools", console_output=True)
logger = logging.getLogger(__name__)

# HARDCODED TARGET FOR D&D PERSONA
# This ensures we always populate the correct D&D Vector DB without complex imports
DND_CHROMA_PATH = str(project_root / "databases" / "dnd" / "chroma_db_store")
DND_COLLECTION = "orion_semantic_memory"

def flatten_item(item: dict) -> str:
    """
    Creates a rich, searchable text representation of a 5eTools JSON object.
    """
    name = item.get("name", "Unknown")
    item_type = item.get("type", "Unknown")
    source = item.get("source", "Unknown")
    
    parts = [f"{name} is a {item_type} from {source}."]
    
    # Add level/school for spells
    if item_type == "spell":
        level = item.get("level", 0)
        school = item.get("school", "")
        parts.append(f"Level {level} {school} magic.")
        if "time" in item:
            time_arr = item["time"]
            if time_arr and isinstance(time_arr, list):
                t = time_arr[0]
                parts.append(f"Casting time: {t.get('number')} {t.get('unit')}.")
    
    # Flatten entries
    entries = item.get("entries", [])
    if entries and isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, str):
                parts.append(entry)
            elif isinstance(entry, dict) and "entries" in entry:
                # Handle nested entries (like "At Higher Levels")
                sub_entries = entry["entries"]
                if isinstance(sub_entries, list) and all(isinstance(se, str) for se in sub_entries):
                    parts.append(entry.get("name", "") + ": " + " ".join(sub_entries))
                    
    # Clean up formatting tokens like {@damage 8d6} -> 8d6
    text = " ".join(parts)
    text = re.sub(r'\{@[a-z]+\s([^}]+)\}', r'\1', text)
    
    return text

def run_5etools_embedding_sync():
    """
    Ingests all loaded 5eTools data into the D&D ChromaDB for semantic search.
    """
    logger.info(f"Targeting D&D Vector DB at: {DND_CHROMA_PATH}")
    logger.info(f"Collection Name: {DND_COLLECTION}")

    try:
        # Check if the directory exists
        if not Path(DND_CHROMA_PATH).parent.exists():
            logger.error(f"Error: Directory '{Path(DND_CHROMA_PATH).parent}' not found. Ensure databases/dnd/ exists.")
            return

        chroma_client = chromadb.PersistentClient(path=DND_CHROMA_PATH)
        collection = chroma_client.get_or_create_collection(name=DND_COLLECTION)
        logger.info(f"Successfully connected to ChromaDB.")
    except Exception as e:
        logger.error(f"Fatal: Could not connect to ChromaDB at '{DND_CHROMA_PATH}'. Error: {e}")
        return

    ids = []
    documents = []
    metadatas = []
    seen_ids = set()

    logger.info("Gathering 5eTools data for ingestion...")
    for col_name in loader.collections_map.keys():
        items = loader.get_collection(col_name)
        if not items:
            continue
            
        logger.info(f"Processing {len(items)} items from collection '{col_name}'...")
        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue
            
            if item_id in seen_ids:
                # logger.debug(f"Skipping duplicate ID: {item_id}")
                continue
            seen_ids.add(item_id)
            
            flat_text = flatten_item(item)
            
            ids.append(item_id)
            documents.append(flat_text)
            metadatas.append({
                "source_table": "5etools",
                "item_type": item.get("type", "unknown"),
                "source": item.get("source", "unknown")
            })

    if not ids:
        logger.warning("No items found to ingest. Ensure data/5eTools/data/ is populated.")
        return

    logger.info(f"Generated {len(ids)} documents. Starting batch upsert...")

    # Batching to avoid memory issues and handle compaction errors
    # Reduced batch size to 100 and added a delay to prevent "Failed to pull logs from log store" errors
    import time
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i + batch_size]
        batch_docs = documents[i:i + batch_size]
        batch_metas = metadatas[i:i + batch_size]
        
        try:
            collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_metas
            )
            logger.info(f"Successfully upserted batch {i//batch_size + 1}/{len(ids)//batch_size + 1}")
            # Small delay to allow ChromaDB compaction to complete
            time.sleep(0.5) 
        except Exception as e:
            logger.error(f"Error upserting batch {i//batch_size + 1}: {e}")
            # If a batch fails, wait longer before trying the next one
            time.sleep(2)

    logger.info("5eTools Semantic Ingestion Complete for the 'dnd' persona.")

if __name__ == "__main__":
    run_5etools_embedding_sync()
