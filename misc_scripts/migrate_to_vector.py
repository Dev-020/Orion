import sqlite3
import chromadb
import os
import json
import logging
import hashlib

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- DATABASE AND COLLECTION CONFIGURATION ---
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orion_database.sqlite")
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db_store")
COLLECTION_NAME = "orion_semantic_memory"

# --- DATA PROCESSING FUNCTIONS ---

def process_deep_memory(conn):
    """
    Processes the deep_memory table, yielding documents and metadata for each row.
    """
    logging.info("Processing table: deep_memory")
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, user_name, timestamp, prompt_text, response_text, attachments_metadata FROM deep_memory")
    
    for row in cursor.fetchall():
        doc = f"Conversation from {row['timestamp']} with user {row['user_name']}. User asked: '{row['prompt_text']}'. Orion responded: '{row['response_text']}'"
        meta = {
            'source_table': 'deep_memory', 
            'source_id': str(row['id']), 
            'user_id': str(row['user_id']), 
            'user_name': row['user_name'], 
            'timestamp': row['timestamp'],
            'attachments': row['attachments_metadata'] # Added attachments_metadata
        }
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

def _recursively_process_entry(node, manifest_keys, full_text_chunks, metadata, path_prefix=""):
    """
    Recursively processes a JSON node to perform two tasks in a single pass:
    1. Extracts all key-value pairs into 'full_text_chunks' for the semantic document.
    2. Identifies and extracts metadata into the 'metadata' object and updates 'manifest_keys'.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            new_path = f"{path_prefix}.{key}" if path_prefix else key
            _recursively_process_entry(value, manifest_keys, full_text_chunks, metadata, new_path)

    elif isinstance(node, list):
        is_simple_list = all(not isinstance(item, (dict, list)) for item in node)
        if is_simple_list and path_prefix:
            # 1. Add to full text
            serialized_list = json.dumps(node)
            full_text_chunks.append(f"{path_prefix}: {serialized_list}")
            # 2. Add to metadata
            metadata[path_prefix] = serialized_list
            if path_prefix not in manifest_keys:
                # MODIFIED: Removed sample_values
                manifest_keys[path_prefix] = {"count": 0, "type": "list"}
            manifest_keys[path_prefix]["count"] += 1
        else:  # It's a list of complex objects
            for item in node:
                # MODIFIED: Generalize path for items in a list
                item_path = f"{path_prefix}[*]"
                _recursively_process_entry(item, manifest_keys, full_text_chunks, metadata, item_path)

    else:  # It's a simple value (str, int, bool, etc.)
        # 1. Add to full text chunk
        if path_prefix:
            full_text_chunks.append(f"{path_prefix}: {node}")
        else:
            full_text_chunks.append(str(node))

        # 2. Apply heuristic to see if it's also metadata
        is_metadata = False
        if isinstance(node, (int, float, bool)) or node is None:
            is_metadata = True
        elif isinstance(node, str) and node.strip():
            if len(node.split()) < METADATA_WORD_LIMIT and '\n' not in node:
                is_metadata = True

        if is_metadata and path_prefix:
            metadata[path_prefix] = node
            if path_prefix not in manifest_keys:
                # MODIFIED: Removed sample_values
                manifest_keys[path_prefix] = {"count": 0, "type": get_metadata_type(node)}
            manifest_keys[path_prefix]["count"] += 1

def process_knowledge_base(conn, manifest_keys):
    """
    Processes the knowledge_base table using a single, efficient recursive function
    to create both a full-text document and rich metadata for filtering.
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
            _recursively_process_entry(data_json, manifest_keys, full_text_chunks, meta)

            # Add base metadata to manifest tracking
            for key in ["type", "name", "source"]:
                if meta.get(key) is not None:
                    if key not in manifest_keys:
                        # MODIFIED: Removed sample_values
                        manifest_keys[key] = {"count": 0, "type": "string"}
                    manifest_keys[key]["count"] += 1

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

    # --- Initialize Manifest ---
    knowledge_base_manifest = {
        "total_entries_processed": 0,
        "discovered_metadata_keys": {}
    }

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
    
    # --- Process knowledge_base separately to handle manifest ---
    # We count entries processed for the manifest, so we track it here.
    kb_entries_processed = 0
    try:
        for doc, meta, chroma_id in process_knowledge_base(sqlite_conn, knowledge_base_manifest["discovered_metadata_keys"]):
            all_docs.append(doc)
            all_metadatas.append(meta)
            all_ids.append(chroma_id)
            kb_entries_processed += 1
    except sqlite3.Error as e:
        logging.error(f"Error processing with process_knowledge_base: {e}")
    
    knowledge_base_manifest["total_entries_processed"] = kb_entries_processed

    # --- Process other tables ---
    processing_functions = [
        process_deep_memory,
        process_long_term_memory,
        process_active_memory,
        process_user_profiles
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


    # --- Finalize and Save Manifest ---
    logging.info("Finalizing knowledge base metadata manifest...")
    # MODIFIED: No longer need to process sample_values
    
    try:
        with open(MANIFEST_PATH, 'w') as f:
            json.dump(knowledge_base_manifest, f, indent=2)
        logging.info(f"Successfully generated metadata manifest at: {MANIFEST_PATH}")
    except IOError as e:
        logging.error(f"Error writing manifest file to {MANIFEST_PATH}: {e}")

    # --- Cleanup ---
    sqlite_conn.close()
    logging.info("SQLite connection closed. Migration process finished.")

if __name__ == "__main__":
    main()
