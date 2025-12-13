import argparse
import hashlib
import json
import logging
from pathlib import Path
import chromadb
import sys

# Add the project root to the Python path to enable imports from main_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))

from main_utils import config as cfg

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- CORE FUNCTIONS ---

def generate_new_state_from_markdown(file_path: Path):
    """
    Parses a Markdown file, generating chunks, metadata, and reproducible IDs.
    """
    source_name = file_path.name
    ids, documents, metadatas = [], [], []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_headers = []
    current_content = []

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('#'):
            if current_content and current_headers:
                header_path = "::".join(h for h, l in current_headers)
                unique_string = f"{source_name}::{header_path}"
                chunk_id = hashlib.sha256(unique_string.encode()).hexdigest()
                
                breadcrumb = " > ".join(h for h, l in current_headers)
                document_text = f"{breadcrumb}\n\n{''.join(current_content).strip()}"
                
                metadata = {
                    "source": str(source_name),
                    "section_hierarchy": json.dumps([str(h) for h, l in current_headers[:-1]]),
                    "current_section": str(current_headers[-1][0])
                }
                logging.info(f"Generated metadata: {metadata}")
                
                ids.append(chunk_id)
                documents.append(document_text)
                metadatas.append(metadata)

            level = len(stripped_line.split(' ')[0])
            header_text = stripped_line[level:].strip()
            
            current_headers = [h for h in current_headers if h[1] < level]
            current_headers.append((header_text, level))
            current_content = []
        
        else:
            current_content.append(line)

    if current_content and current_headers:
        header_path = "::".join(h for h, l in current_headers)
        unique_string = f"{source_name}::{header_path}"
        chunk_id = hashlib.sha256(unique_string.encode()).hexdigest()
        
        breadcrumb = " > ".join(h for h, l in current_headers)
        document_text = f"{breadcrumb}\n\n{''.join(current_content).strip()}"
        
        metadata = {
            "source": str(source_name),
            "section_hierarchy": json.dumps([str(h) for h, l in current_headers[:-1]]),
            "current_section": str(current_headers[-1][0])
        }
        logging.info(f"Generated metadata: {metadata}")
        
        ids.append(chunk_id)
        documents.append(document_text)
        metadatas.append(metadata)

    return ids, documents, metadatas

def get_old_state_ids(collection: chromadb.Collection, source_name: str) -> set:
    """
    Retrieves all existing document IDs for a given source from the collection.
    """
    try:
        existing_docs = collection.get(where={"source": source_name}, include=[])
        return set(existing_docs['ids'])
    except Exception as e:
        logging.error(f"Error fetching old state IDs for source '{source_name}': {e}")
        return set()

# --- MAIN ORCHESTRATION ---

def run_embedding_sync(file_path_str: str):
    """
    Performs the "Intelligent Sync" of a Markdown document to ChromaDB.
    This function is designed to be imported and called from other scripts.
    """
    file_path = Path(file_path_str)
    source_name = file_path.name

    if not file_path.is_file() or not file_path.name.lower().endswith(('.md', '.markdown')):
        logging.error(f"Error: Provided path '{file_path_str}' is not a valid Markdown file. Skipping embedding.")
        return

    logging.info(f"Starting 'Intelligent Sync' for document: {source_name}")

    try:
        chroma_client = chromadb.PersistentClient(path=str(cfg.CHROMA_DB_PATH))
        collection = chroma_client.get_or_create_collection(name=cfg.COLLECTION_NAME)
        logging.info(f"Successfully connected to ChromaDB collection '{cfg.COLLECTION_NAME}'.")
    except Exception as e:
        logging.error(f"Fatal: Could not connect to ChromaDB at '{cfg.CHROMA_DB_PATH}'. Error: {e}")
        return

    logging.info(f"Step 1: Generating new state from '{source_name}'...")
    new_ids, new_docs, new_metadatas = generate_new_state_from_markdown(file_path)
    new_ids_set = set(new_ids)
    logging.info(f"Generated {len(new_ids)} chunks from the source file.")

    logging.info(f"Step 2: Fetching old state for '{source_name}' from database...")
    old_ids_set = get_old_state_ids(collection, source_name)
    logging.info(f"Found {len(old_ids_set)} existing chunks for this source.")

    orphans_to_delete = list(old_ids_set - new_ids_set)
    if orphans_to_delete:
        logging.info(f"Step 3a: Deleting {len(orphans_to_delete)} orphan chunks...")
        try:
            collection.delete(ids=orphans_to_delete)
            logging.info("Deletion successful.")
        except Exception as e:
            logging.error(f"Error deleting orphan chunks: {e}")
    else:
        logging.info("Step 3a: No orphan chunks to delete.")

    if new_ids:
        logging.info(f"Step 3b: Upserting {len(new_ids)} chunks into the database in batches...")
        
        # --- Batching Logic ---
        MAX_BATCH_SIZE = 4000
        
        def chunks(lst, n):
            """Yield successive n-sized chunks from lst."""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        ids_gen = chunks(new_ids, MAX_BATCH_SIZE)
        docs_gen = chunks(new_docs, MAX_BATCH_SIZE)
        metadatas_gen = chunks(new_metadatas, MAX_BATCH_SIZE)
        
        total_chunks = len(new_ids)
        processed_chunks = 0

        try:
            for id_batch, doc_batch, meta_batch in zip(ids_gen, docs_gen, metadatas_gen):
                collection.upsert(
                    ids=id_batch,
                    documents=doc_batch,
                    metadatas=meta_batch
                )
                processed_chunks += len(id_batch)
                logging.info(f"Upserted batch. {processed_chunks}/{total_chunks} chunks processed.")
            logging.info("All chunks upserted successfully.")
        except Exception as e:
            logging.error(f"An error occurred during the upsert process: {e}", exc_info=True)
            
    else:
        logging.info("Step 3b: No new chunks to upsert.")

    logging.info(f"'Intelligent Sync' for {source_name} complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Embed a Markdown document into the ChromaDB vector store.')
    parser.add_argument('file_path', type=str, help='The absolute path to the Markdown file to process.')
    parser.add_argument('--persona', type=str, default='default', help='The persona to use for database paths.')
    args = parser.parse_args()

    # When run as a standalone script, initialize with a persona.
    # This ensures that the config variables are set correctly.
    from main_utils.main_functions import initialize_persona
    initialize_persona(args.persona)

    run_embedding_sync(args.file_path)