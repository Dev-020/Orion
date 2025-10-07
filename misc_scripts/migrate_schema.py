import json
import sqlite3
import os
import chromadb
import logging

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "instructions", "deep_schema_analysis.json")
DB_PATH = os.path.join(BASE_DIR, "orion_database.sqlite")
CHROMA_DB_PATH = os.path.join(BASE_DIR, "chroma_db_store")
# Use the main collection to integrate schema data with other vectorized information
COLLECTION_NAME = "orion_semantic_memory" 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- SQLITE MIGRATION ---
def migrate_to_sqlite():
    """
    Parses deep_schema_analysis.json and migrates its content into the
    'knowledge_schema' table in the SQLite database. This function ensures
    the SQLite table is up-to-date before vectorization.
    """
    logging.info("--- Starting SQLite Schema Migration ---")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        logging.info("Dropping old 'knowledge_schema' table if it exists...")
        cursor.execute("DROP TABLE IF EXISTS knowledge_schema;")
        
        logging.info("Creating new 'knowledge_schema' table...")
        cursor.execute("""
        CREATE TABLE knowledge_schema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            count INTEGER NOT NULL,
            data_type TEXT
        );
        """)
        
        logging.info("Creating index on 'knowledge_schema' table...")
        cursor.execute("CREATE INDEX idx_schema_type_count ON knowledge_schema (type, count DESC);")

        logging.info(f"Loading schema data from: {JSON_PATH}")
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            schema_data = json.load(f)
        
        logging.info("Preparing data for insertion...")
        rows_to_insert = []
        for type_name, paths in schema_data.items():
            for path_name, details in paths.items():
                rows_to_insert.append((
                    type_name,
                    path_name,
                    details.get('count', 0),
                    details.get('type', 'unknown')
                ))

        logging.info(f"Inserting {len(rows_to_insert)} schema paths into SQLite...")
        cursor.executemany(
            "INSERT INTO knowledge_schema (type, path, count, data_type) VALUES (?, ?, ?, ?)",
            rows_to_insert
        )

        conn.commit()
        logging.info("SQLite migration completed successfully.")
    except Exception as e:
        logging.error(f"An error occurred during SQLite migration: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            logging.info("SQLite connection closed.")

# --- VECTOR DB MIGRATION ---
def process_knowledge_schema(conn):
    """
    Processes the knowledge_schema table from SQLite, yielding documents and 
    metadata formatted for ChromaDB, consistent with other data sources.
    """
    logging.info("Processing table: knowledge_schema for vectorization")
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, path, count, data_type FROM knowledge_schema")
    
    for row in cursor.fetchall():
        doc = f"Schema entry. Type: {row['type']}. Path: {row['path']}. Usage count: {row['count']}. Data type: {row['data_type']}."
        # Metadata now includes source_table and source_id for consistency
        meta = {
            'source_table': 'knowledge_schema',
            'source_id': str(row['id']),
            'type': row['type'],
            'path': row['path'],
            'count': row['count'],
            'data_type': row['data_type']
        }
        # Chroma ID is unique to the source table and ID
        chroma_id = f"knowledge_schema_{row['id']}"
        yield doc, meta, chroma_id

def migrate_knowledge_schema_to_vector():
    """
    Orchestrates the migration of the 'knowledge_schema' table from SQLite 
    to the main ChromaDB collection.
    """
    logging.info("--- Starting Knowledge Schema to Vector DB Migration ---")
    
    try:
        sqlite_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        sqlite_conn.row_factory = sqlite3.Row
        logging.info("Successfully connected to SQLite database in read-only mode.")
    except sqlite3.Error as e:
        logging.error(f"Error connecting to SQLite database: {e}")
        return

    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        # Get or create the main collection. We do not delete it, as it contains other data.
        collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)
        logging.info(f"Successfully connected to ChromaDB and retrieved/created collection '{COLLECTION_NAME}'.")
    except Exception as e:
        logging.error(f"Error connecting to ChromaDB: {e}", exc_info=True)
        sqlite_conn.close()
        return

    documents, metadatas, ids = [], [], []
    try:
        for doc, meta, chroma_id in process_knowledge_schema(sqlite_conn):
            documents.append(doc)
            metadatas.append(meta)
            ids.append(chroma_id)
    except sqlite3.Error as e:
        logging.error(f"Error processing knowledge_schema: {e}", exc_info=True)
        sqlite_conn.close()
        return
        
    if not documents:
        logging.info("No new documents from knowledge_schema to process.")
        sqlite_conn.close()
        return

    # Upsert data in batches to avoid overwhelming the database
    MAX_BATCH_SIZE = 4000
    total_docs = len(documents)
    logging.info(f"Upserting {total_docs} schema documents to ChromaDB in batches...")
    
    for i in range(0, total_docs, MAX_BATCH_SIZE):
        batch_end = i + MAX_BATCH_SIZE
        doc_batch = documents[i:batch_end]
        meta_batch = metadatas[i:batch_end]
        id_batch = ids[i:batch_end]
        
        try:
            collection.upsert(
                documents=doc_batch,
                metadatas=meta_batch,
                ids=id_batch
            )
            logging.info(f"Upserted batch. {min(batch_end, total_docs)}/{total_docs} documents processed.")
        except Exception as e:
            logging.error(f"An error occurred during ChromaDB upsert: {e}", exc_info=True)

    sqlite_conn.close()
    logging.info("Knowledge schema migration to vector DB finished.")

# --- MAIN ORCHESTRATION ---
if __name__ == "__main__":
    logging.info("Starting full schema migration process...")
    # Step 1: Refresh the SQLite table from the JSON source.
    migrate_to_sqlite() 
    # Step 2: Upsert the content of the refreshed SQLite table into the vector DB.
    migrate_knowledge_schema_to_vector()
    logging.info("All schema migration tasks finished.")