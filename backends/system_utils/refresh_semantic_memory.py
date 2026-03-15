import sqlite3
import json
import logging
import hashlib
import zlib
from pathlib import Path
from datetime import datetime, timezone
import sys
import chromadb

# Add the backends directory to the Python path to resolve internal modules correctly
project_root = Path(__file__).resolve().parent.parent.parent
backends_root = project_root / "backends"
if str(backends_root) not in sys.path:
    sys.path.insert(0, str(backends_root))

from main_utils import config as cfg
from main_utils.orion_logger import setup_logging

# --- CONFIGURATION ---
setup_logging("RefreshSemanticMemory", console_output=True)
logger = logging.getLogger(__name__)

# --- ENRICHMENT LOGIC (from historical migrate_to_vector.py) ---

def process_deep_memory(conn):
    """Processes deep_memory with tool call enrichment."""
    logger.info("  - Processing table: deep_memory")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deep_memory")
    
    for row_obj in cursor.fetchall():
        row = dict(row_obj)
        tool_summary = ""
        if row.get('function_calls'):
            try:
                function_calls_obj = json.loads(row['function_calls'])
                if isinstance(function_calls_obj, list):
                    summaries = []
                    for content_item in function_calls_obj:
                        if isinstance(content_item, dict) and isinstance(content_item.get('parts'), list):
                            for part in content_item['parts']:
                                if isinstance(part, dict):
                                    if part.get('function_call'):
                                        summaries.append(f"Called function '{part['function_call'].get('name')}'")
                                    elif part.get('function_response'):
                                        summaries.append(f"Received response for '{part['function_response'].get('name')}'")
                    if summaries:
                        tool_summary = f" Actions Taken: [{'; '.join(summaries)}]."
            except (json.JSONDecodeError, TypeError):
                pass

        ts_iso = datetime.fromtimestamp(row.get('timestamp', 0), tz=timezone.utc).isoformat()
        base_doc = f"Conversation from {ts_iso} with user {row.get('user_name', 'Unknown')}. User asked: '{row.get('prompt_text', '')}'. Orion responded: '{row.get('response_text', '')}'"
        doc = base_doc + tool_summary

        essential_metadata_keys = [
            'session_id', 'user_id', 'user_name', 'timestamp', 'token', 'model_source'
        ]
        meta = {'source_table': 'deep_memory', 'source_id': str(row['id'])}
        for key in essential_metadata_keys:
            if key in row and row[key] is not None:
                meta[key] = row[key]

        yield doc, meta, f"deep_memory_{row['id']}"

def process_long_term_memory(conn):
    """Processes long_term_memory."""
    logger.info("  - Processing table: long_term_memory")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM long_term_memory")

    for row_obj in cursor.fetchall():
        row = dict(row_obj)
        content = f"{row.get('description', '')} {row.get('snippet', '')}".strip()
        doc = f"Memory Title: {row.get('title', '')}. Category: {row.get('category', '')}. Date: {row.get('date', '')}. Contents: {content}"
        meta = {
            'source_table': 'long_term_memory', 
            'source_id': str(row['event_id']), 
            'category': row.get('category', ''), 
            'date': row.get('date', '')
        }
        yield doc, meta, f"long_term_memory_{row['event_id']}"

def process_user_profiles(conn):
    """Processes user_profiles and splits notes into separate documents."""
    logger.info("  - Processing table: user_profiles")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles")

    for row_obj in cursor.fetchall():
        row = dict(row_obj)
        # 1. Base Profile Document
        aliases = row.get('aliases', '[]')
        try:
            aliases_list = json.loads(aliases)
            aliases_str = ", ".join(aliases_list) if aliases_list else "N/A"
        except:
            aliases_str = "N/A"
            
        doc_user = f"User profile for {row['user_name']} (also known as: {aliases_str}). First seen on {row['first_seen']}."
        meta_user = {
            'source_table': 'user_profiles',
            'source_id': str(row['user_id']),
            'user_id': str(row['user_id']),
            'user_name': row['user_name']
        }
        yield doc_user, meta_user, f"user_profile_{row['user_id']}"

        # 2. Individual Notes
        if row.get('notes'):
            try:
                notes_list = json.loads(row['notes'])
                if isinstance(notes_list, list):
                    for note_obj in notes_list:
                        note_text = note_obj.get('note', '')
                        if not note_text: continue
                        
                        doc_note = f"Note about user {row['user_name']}: {note_text}"
                        unique_content = f"{row['user_id']}{note_obj.get('timestamp', '')}{note_text}"
                        hash_id = hashlib.sha1(unique_content.encode('utf-8')).hexdigest()
                        
                        meta_note = {
                            'source_table': 'user_profiles',
                            'source_id': str(row['user_id']),
                            'user_id': str(row['user_id']),
                            'user_name': row['user_name'],
                            'note_category': note_obj.get('category'),
                            'note_timestamp': note_obj.get('timestamp')
                        }
                        yield doc_note, meta_note, f"user_note_{hash_id}"
            except:
                pass

def process_active_memory(conn):
    """Processes active_memory (rulings)."""
    logger.info("  - Processing table: active_memory")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM active_memory")

    for row_obj in cursor.fetchall():
        row = dict(row_obj)
        doc = f"Ruling for '{row['topic']}'. Question: {row['prompt']}. Ruling: {row['ruling']}"
        unique_content = f"{row['topic']}{row['prompt']}"
        hash_id = hashlib.sha1(unique_content.encode('utf-8')).hexdigest()
        
        meta = {
            'source_table': 'active_memory', 
            'source_id': hash_id,
            'topic': row['topic'],
            'status': row['status']
        }
        yield doc, meta, f"active_memory_{hash_id}"

# --- MAIN REFRESH LOGIC ---

def refresh_semantic_memory(persona: str, wipe: bool = False):
    """
    Rebuilds the Vector DB from the SQLite database for a specific persona.
    """
    databases_dir = project_root / 'databases'
    persona_dir = databases_dir / persona
    db_file = persona_dir / 'orion_database.sqlite'
    chroma_dir = persona_dir / 'chroma_db_store'

    if not db_file.exists():
        logger.error(f"SQLite database not found for persona '{persona}' at {db_file}")
        return

    logger.info(f"--- REFRESHING SEMANTIC MEMORY: {persona.upper()} ---")
    managed_tables = ['deep_memory', 'long_term_memory', 'user_profiles', 'active_memory']

    # 1. Initialize Chroma Client
    try:
        chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
        collection_name = "orion_semantic_memory"
        
        if wipe:
            logger.info(f"WIPE FLAG DETECTED: Deleting entire collection '{collection_name}' to reclaim space...")
            try:
                chroma_client.delete_collection(name=collection_name)
            except:
                pass
            collection = chroma_client.create_collection(name=collection_name)
        else:
            collection = chroma_client.get_or_create_collection(name=collection_name)
            logger.info(f"Surgical Refresh: Deleting existing entries for {managed_tables}...")
            # Delete only the items managed by this script
            for table in managed_tables:
                collection.delete(where={"source_table": table})
            
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB: {e}")
        return

    # 2. Connect to SQLite and Vacuum (Vacuum helps shrink file size after deletes)
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        logger.info("SQLite connected. Vacuuming...")
        conn.execute("VACUUM")
    except Exception as e:
        logger.error(f"SQLite error: {e}")
        return

    # 3. Process Tables
    all_docs, all_metas, all_ids = [], [], []
    processors = [
        process_deep_memory,
        process_long_term_memory,
        process_user_profiles,
        process_active_memory
    ]

    for processor in processors:
        try:
            for doc, meta, vdb_id in processor(conn):
                all_docs.append(doc)
                all_metas.append(meta)
                all_ids.append(vdb_id)
        except Exception as e:
            logger.warning(f"Processor {processor.__name__} failed: {e}")

    # 4. Batch Upsert to ChromaDB
    if not all_docs:
        logger.info("No data found in SQLite to index.")
        conn.close()
        return

    logger.info(f"Indexing {len(all_docs)} documents into ChromaDB...")
    import time
    batch_size = 100
    for i in range(0, len(all_docs), batch_size):
        try:
            collection.upsert(
                ids=all_ids[i:i+batch_size],
                documents=all_docs[i:i+batch_size],
                metadatas=all_metas[i:i+batch_size]
            )
            logger.info(f"  - Indexed {min(i+batch_size, len(all_docs))}/{len(all_docs)}")
            time.sleep(0.1) # Prevent log store overwhelm
        except Exception as e:
            logger.error(f"Batch upsert error: {e}")

    conn.close()
    logger.info(f"--- SEMANTIC MEMORY REFRESH COMPLETE: {persona.upper()} ---")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Refresh Vector DB from SQLite for a persona.')
    parser.add_argument('persona', type=str, help='The persona to refresh (e.g., default, dnd).')
    
    args = parser.parse_args()
    refresh_semantic_memory(args.persona)
