import sqlite3
import chromadb
import os
import json
import logging
import hashlib
import zlib
from datetime import datetime, timezone

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- DATABASE AND COLLECTION CONFIGURATION ---
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'databases', 'default', 'orion_database.sqlite')
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'databases', 'default', 'chroma_db_store')
COLLECTION_NAME = "orion_semantic_memory"

# --- DATA PROCESSING FUNCTIONS ---

def process_deep_memory(conn):
    """
    Processes the deep_memory table, yielding documents and metadata for each row.
    """
    logging.info("Processing table: deep_memory (with enriched document logic)")
    cursor = conn.cursor()
    # Fetch all relevant columns, including the new JSON ones
    cursor.execute("SELECT * FROM deep_memory")
    
    for row_obj in cursor.fetchall():
        # --- 1. Document Enrichment (same as functions.py) ---
        row = dict(row_obj) # Convert the immutable sqlite3.Row to a mutable dictionary
        tool_summary = ""
        if row['function_calls']:
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
                pass # Ignore if parsing fails

        vdb_context_text = ""
        if row['vdb_context']:
            vdb_context_content = row['vdb_context']
            # --- Decompression Logic (mirroring functions.py) ---
            # Check if the context is a bytes object, which indicates it's compressed.
            if isinstance(vdb_context_content, bytes):
                try:
                    vdb_context_content = zlib.decompress(vdb_context_content).decode('utf-8')
                    # CRITICAL FIX: Update the row dictionary itself with the decompressed string.
                    # This ensures the metadata population step below uses the correct string value, not the raw bytes.
                    row['vdb_context'] = vdb_context_content
                except zlib.error:
                    logging.warning(f"Could not decompress vdb_context for deep_memory id {row['id']}. Skipping context for this entry.")
                    vdb_context_content = ""
                    row['vdb_context'] = "" # Ensure the row is also updated with an empty string
            
            try:
                vdb_context_obj = json.loads(vdb_context_content or '{}')
                if isinstance(vdb_context_obj, dict) and vdb_context_obj.get('documents') and vdb_context_obj['documents'][0]:
                    context_docs = ' | '.join(filter(None, vdb_context_obj['documents'][0]))
                    vdb_context_text = f" Context Used: [{context_docs}]." if context_docs else ""
            except (json.JSONDecodeError, TypeError):
                pass # Ignore if parsing fails

        ts_iso = datetime.fromtimestamp(row['timestamp'] or 0, tz=timezone.utc).isoformat()
        base_doc = f"Conversation from {ts_iso} with user {row['user_name']}. User asked: '{row['prompt_text']}'. Orion responded: '{row['response_text']}'"
        doc = base_doc + tool_summary + vdb_context_text

        # --- 2. Selective Metadata Population (mirroring functions.py) ---
        essential_metadata_keys = [
            'source_table', 'source_id', 'session_id', 'user_id', 'user_name',
            'timestamp', 'token', 'function_calls', 'vdb_context', 'attachments_metadata'
        ]
        meta = {
            'source_table': 'deep_memory',
            'source_id': str(row['id'])
        }
        for key in essential_metadata_keys:
            if key in row.keys() and key not in meta:
                meta[key] = row[key]

        # Generate a unique ID for the ChromaDB entry
        chroma_id = f"deep_memory_{row['id']}"
        yield doc, meta, chroma_id

def process_long_term_memory(conn):
    """
    Processes the long_term_memory table, yielding documents and metadata for each row.
    """
    logging.info("Processing table: long_term_memory")
    cursor = conn.cursor()
    cursor.execute("SELECT event_id, date, title, category, description, snippet FROM long_term_memory")

    for row in cursor.fetchall():
        # Combine description and snippet for richer context, handling None values
        content = f"{row['description'] or ''} {row['snippet'] or ''}".strip()
        doc = f"Memory Title: {row['title']}. Category: {row['category']}. Date: {row['date']}. Contents: {content}"
        meta = {
            'source_table': 'long_term_memory', 
            'source_id': str(row['event_id']), 
            'category': row['category'], 
            'date': row['date']
        }
        chroma_id = f"long_term_memory_{row['event_id']}"
        yield doc, meta, chroma_id

def process_active_memory(conn):
    """
    Processes the active_memory table, yielding documents and metadata for each row.
    """
    logging.info("Processing table: active_memory")
    cursor = conn.cursor()
    cursor.execute("SELECT topic, prompt, ruling, status, last_modified FROM active_memory")

    for row in cursor.fetchall():
        doc = f"D&D Ruling for '{row['topic']}'. Question: {row['prompt']}. Ruling: {row['ruling']}'"
        
        # Generate a stable, unique ID using a hash of the content
        unique_content = f"{row['topic']}{row['prompt']}"
        hash_id = hashlib.sha1(unique_content.encode('utf-8')).hexdigest()
        chroma_id = f"active_memory_{hash_id}"

        meta = {
            'source_table': 'active_memory', 
            'source_id': chroma_id, # Use the generated hash as the source_id
            'topic': row['topic'],
            'status': row['status'], 
            'last_modified': row['last_modified']
        }
        yield doc, meta, chroma_id

def process_knowledge_schema(conn):
    """
    Processes the knowledge_schema table from SQLite, yielding documents and 
    metadata formatted for ChromaDB. (Merged from migrate_schema.py)
    """
    logging.info("Processing table: knowledge_schema")
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, path, count, data_type FROM knowledge_schema")
    
    for row in cursor.fetchall():
        doc = f"Schema entry. Type: {row['type']}. Path: {row['path']}. Usage count: {row['count']}. Data type: {row['data_type']}."
        meta = {
            'source_table': 'knowledge_schema',
            'source_id': str(row['id']),
            'type': row['type'],
            'path': row['path'],
            'count': row['count'],
            'data_type': row['data_type']
        }
        chroma_id = f"knowledge_schema_{row['id']}"
        yield doc, meta, chroma_id

# --- KNOWLEDGE BASE PROCESSING ---

# Heuristics for identifying metadata
METADATA_WORD_LIMIT = 15 # Strings with more words are considered content
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instructions", "metadata_manifest.json")

def get_metadata_type(value):
    """Determines the data type for the manifest."""
    if isinstance(value, bool): return "boolean"
    if isinstance(value, (int, float)): return "number"
    if isinstance(value, list): return "list"
    return "string"

def _recursively_process_entry(node, full_text_chunks, metadata, path_prefix=""):
    """
    Recursively processes a JSON node to extract all key-value pairs into 'full_text_chunks'
    and identify potential metadata fields.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            new_path = f"{path_prefix}.{key}" if path_prefix else key
            _recursively_process_entry(value, full_text_chunks, metadata, new_path)

    elif isinstance(node, list):
        is_simple_list = all(not isinstance(item, (dict, list)) for item in node)
        if is_simple_list and path_prefix:
            serialized_list = json.dumps(node)
            full_text_chunks.append(f"{path_prefix}: {serialized_list}")
            metadata[path_prefix] = serialized_list
        else:  # It's a list of complex objects
            for item in node:
                item_path = f"{path_prefix}[*]"
                _recursively_process_entry(item, full_text_chunks, metadata, item_path)

    else:  # It's a simple value (str, int, bool, etc.)
        if path_prefix:
            full_text_chunks.append(f"{path_prefix}: {node}")
        else:
            full_text_chunks.append(str(node))

        is_metadata = False
        if isinstance(node, (int, float, bool)) or node is None:
            is_metadata = True
        elif isinstance(node, str) and node.strip():
            if len(node.split()) < METADATA_WORD_LIMIT and '\n' not in node:
                is_metadata = True

        if is_metadata and path_prefix:
            metadata[path_prefix] = node

def process_knowledge_base(conn):
    """
    Processes the knowledge_base table to create a full-text document and rich metadata.
    """
    logging.info("Processing table: knowledge_base")
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, name, source, data FROM knowledge_base")

    for row in cursor.fetchall():
        try:
            data_json = json.loads(row['data']) if row['data'] else {}
            
            full_text_chunks = []
            meta = {
                'source_table': 'knowledge_base',
                'source_id': str(row['id']),
                'type': row['type'],
                'name': row['name'],
                'source': row['source']
            }

            # Use the single recursive function to populate both text and metadata
            _recursively_process_entry(data_json, full_text_chunks, meta)

            doc_content = ". ".join(full_text_chunks)
            doc = f"Entry Name: {row['name']}. Type: {row['type']}. Source: {row['source']}. Details: {doc_content}"
            
            chroma_id = f"knowledge_base_{row['id']}"
            yield doc, meta, chroma_id

        except json.JSONDecodeError:
            logging.warning(f"Could not parse data JSON for knowledge_base entry {row['id']}. Skipping.")
            continue
        except Exception as e:
            logging.error(f"An unexpected error occurred processing knowledge_base entry {row['id']}: {e}")
            continue

def process_user_profiles(conn):
    """
    Processes the user_profiles table. Creates a primary document for each user 
    and separate documents for each note within their 'notes' JSON field.
    """
    logging.info("Processing table: user_profiles")
    cursor = conn.cursor()
    # Updated query to include aliases and first_seen
    cursor.execute("SELECT user_id, user_name, aliases, first_seen, notes FROM user_profiles")

    for row in cursor.fetchall():
        # --- Create a primary document for the user profile itself ---
        aliases_str = ", ".join(json.loads(row['aliases'])) if row['aliases'] else "N/A"
        doc_user = f"User profile for {row['user_name']} (also known as: {aliases_str}). First seen on {row['first_seen']}."
        meta_user = {
            'source_table': 'user_profiles',
            'source_id': str(row['user_id']),
            'user_id': str(row['user_id']),
            'user_name': row['user_name'],
            'aliases': row['aliases'], # Store original JSON string
            'first_seen': row['first_seen']
        }
        chroma_id_user = f"user_profile_{row['user_id']}"
        yield doc_user, meta_user, chroma_id_user

        # --- Process each note in the 'notes' field ---
        if not row['notes']:
            continue

        try:
            notes_list = json.loads(row['notes'])
            if not isinstance(notes_list, list):
                logging.warning(f"Could not process notes for user {row['user_name']}: JSON is not a list.")
                continue

            for note_obj in notes_list:
                note_text = note_obj.get('note', '')
                if not note_text:
                    continue

                doc_note = f"Note about user {row['user_name']}: {note_text}"
                
                # Generate a stable, unique ID for each individual note
                unique_content = f"{row['user_id']}{note_obj.get('timestamp', '')}{note_text}"
                hash_id = hashlib.sha1(unique_content.encode('utf-8')).hexdigest()
                chroma_id_note = f"user_note_{hash_id}"

                meta_note = {
                    'source_table': 'user_profiles',
                    'source_id': str(row['user_id']), # Link back to the user
                    'user_id': str(row['user_id']),
                    'user_name': row['user_name'],
                    'aliases': row['aliases'], # Inherit parent data
                    'first_seen': row['first_seen'], # Inherit parent data
                    'note_category': note_obj.get('category'),
                    'note_timestamp': note_obj.get('timestamp'),
                    'note_tags': json.dumps(note_obj.get('tags', []))
                }
                yield doc_note, meta_note, chroma_id_note

        except json.JSONDecodeError:
            logging.warning(f"Could not parse notes for user {row['user_name']}: Invalid JSON.")
            continue

# --- MAIN ORCHESTRATION ---

def main():
    """
    Main function to orchestrate the migration from SQLite to ChromaDB.
    """
    logging.info("Starting vector database migration...")

    # --- Connect to Databases ---
    try:
        sqlite_conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
        sqlite_conn.row_factory = sqlite3.Row
        logging.info("Successfully connected to SQLite database in read-only mode.")
    except sqlite3.Error as e:
        logging.error(f"Error connecting to SQLite database: {e}")
        return

    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        # Let's reset the collection to ensure a clean migration
        chroma_client.delete_collection(name=COLLECTION_NAME)
        logging.info(f"Deleted existing collection '{COLLECTION_NAME}' for a clean migration.")
        collection = chroma_client.create_collection(name=COLLECTION_NAME)
        logging.info(f"Successfully created a new, empty collection '{COLLECTION_NAME}'.")
    except Exception as e:
        logging.warning(f"Could not delete collection (it might not exist, which is fine): {e}")
        try:
            collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)
            logging.info(f"Successfully connected to ChromaDB and retrieved/created collection '{COLLECTION_NAME}'.")
        except Exception as e_inner:
            logging.error(f"Error connecting to ChromaDB: {e_inner}")
            sqlite_conn.close()
            return


    # --- Process and Batch Insert ---
    all_docs = []
    all_metadatas = []
    all_ids = []
    
    # --- Define all processing functions to run ---
    # To refactor only deep_memory, comment out all other functions.
    processing_functions = [
        #process_knowledge_base,
        process_deep_memory,
        process_long_term_memory,
        #process_active_memory,
        process_user_profiles,
        #process_knowledge_schema # Merged from separate script
    ]

    for process_func in processing_functions:
        try:
            for doc, meta, chroma_id in process_func(sqlite_conn):
                all_docs.append(doc)
                all_metadatas.append(meta)
                all_ids.append(chroma_id)
        except sqlite3.Error as e:
            logging.error(f"Error processing with {process_func.__name__}: {e}")
            continue

    if not all_docs:
        logging.info("No documents to process. Migration complete.")
        sqlite_conn.close()
        return

    # --- MODIFIED: Add to ChromaDB in batches ---
    def chunks(lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    # Set a safe batch size, well under the typical limit of ~5461
    MAX_BATCH_SIZE = 4000 

    docs_gen = chunks(all_docs, MAX_BATCH_SIZE)
    metadatas_gen = chunks(all_metadatas, MAX_BATCH_SIZE)
    ids_gen = chunks(all_ids, MAX_BATCH_SIZE)

    total_docs = len(all_docs)
    processed_docs = 0

    logging.info(f"Adding {total_docs} documents to ChromaDB in batches of {MAX_BATCH_SIZE}...")

    try:
        for doc_batch, meta_batch, id_batch in zip(docs_gen, metadatas_gen, ids_gen):
            collection.upsert(
                documents=doc_batch,
                metadatas=meta_batch,
                ids=id_batch
            )
            processed_docs += len(doc_batch)
            logging.info(f"Upserted batch. {processed_docs}/{total_docs} documents processed.")
        
        logging.info("Successfully upserted all documents to ChromaDB.")
    except Exception as e:
        logging.error(f"Error adding documents to ChromaDB: {e}", exc_info=True)

    # --- Cleanup ---
    sqlite_conn.close()
    logging.info("SQLite connection closed. Migration process finished.")

if __name__ == "__main__":
    main()
