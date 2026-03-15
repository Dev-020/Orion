import sqlite3
import os
import shutil
import logging
from pathlib import Path
import sys

# Add the backends directory to the Python path to resolve internal modules correctly
project_root = Path(__file__).resolve().parent.parent.parent
backends_root = project_root / "backends"
if str(backends_root) not in sys.path:
    sys.path.insert(0, str(backends_root))

from main_utils import config as cfg

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TABLES = {
    "deep_memory": """
        CREATE TABLE IF NOT EXISTS deep_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            prompt_text TEXT,
            response_text TEXT,
            attachments_metadata TEXT,
            token INTEGER,
            function_calls TEXT,
            vdb_context TEXT,
            model_source TEXT DEFAULT 'gemini-3-flash'
        );
    """,
    "deep_memory_indexes": [
        "CREATE INDEX IF NOT EXISTS idx_deep_memory_user_id ON deep_memory (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_deep_memory_session_id ON deep_memory (session_id);"
    ],
    "user_profiles": """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL,
            aliases TEXT,
            first_seen TEXT NOT NULL,
            notes TEXT
        );
    """,
    "restart_state": """
        CREATE TABLE IF NOT EXISTS restart_state (
            session_id TEXT PRIMARY KEY,
            history_blob TEXT,
            excluded_ids_blob TEXT
        );
    """,
    "long_term_memory": """
        CREATE TABLE IF NOT EXISTS long_term_memory (
            event_id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            snippet TEXT NOT NULL
        );
    """,
    "long_term_memory_indexes": [
        "CREATE INDEX IF NOT EXISTS idx_ltm_title ON long_term_memory (title);",
        "CREATE INDEX IF NOT EXISTS idx_ltm_category ON long_term_memory (category);"
    ],
    "pending_logs": """
        CREATE TABLE IF NOT EXISTS pending_logs (
            event_id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            snippet TEXT NOT NULL
        );
    """,
    "active_memory": """
        CREATE TABLE IF NOT EXISTS active_memory (
            topic TEXT PRIMARY KEY,
            prompt TEXT,
            ruling TEXT NOT NULL,
            status TEXT NOT NULL,
            last_modified TEXT NOT NULL
        );
    """,
    "instruction_proposals": """
        CREATE TABLE IF NOT EXISTS instruction_proposals (
            proposal_name TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            new_content TEXT NOT NULL,
            diff_text TEXT NOT NULL,
            status TEXT NOT NULL,
            proposal_timestamp TEXT NOT NULL,
            resolution_timestamp TEXT
        );
    """,
    "character_resources": """
        CREATE TABLE IF NOT EXISTS character_resources (
            resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            resource_name TEXT NOT NULL,
            current_value INTEGER NOT NULL,
            max_value INTEGER,
            last_updated TEXT NOT NULL
        );
    """,
    "character_status": """
        CREATE TABLE IF NOT EXISTS character_status (
            status_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            effect_name TEXT NOT NULL,
            effect_details TEXT,
            duration_in_rounds INTEGER,
            timestamp TEXT NOT NULL
        );
    """,
    "knowledge_base": """
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT,
            data TEXT NOT NULL
        );
    """,
    "knowledge_base_indexes": [
        "CREATE INDEX IF NOT EXISTS idx_knowledge_name ON knowledge_base (name);",
        "CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_base (type);"
    ],
    "knowledge_schema": """
        CREATE TABLE IF NOT EXISTS knowledge_schema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            count INTEGER NOT NULL,
            data_type TEXT
        );
    """,
    "diagnostic_test_table": """
        CREATE TABLE IF NOT EXISTS diagnostic_test_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            timestamp TEXT
        );
    """,
    "cache_metadata": """
        CREATE TABLE IF NOT EXISTS cache_metadata (
            persona TEXT NOT NULL,
            model_name TEXT NOT NULL,
            cache_name TEXT NOT NULL,
            instruction_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            ttl_seconds INTEGER DEFAULT 1800,
            PRIMARY KEY (persona, model_name)
        );
    """
}

def initialize_database(persona: str, wipe: bool = False):
    """
    Initializes a fresh database for the given persona with all standard tables and indexes.
    """
    databases_dir = project_root / 'databases'
    persona_dir = databases_dir / persona
    db_file = persona_dir / 'orion_database.sqlite'
    chroma_dir = persona_dir / 'chroma_db_store'

    if wipe:
        logger.info(f"Wiping existing database and vector store for persona '{persona}'...")
        if persona_dir.exists():
            if chroma_dir.exists():
                logger.info(f"Deleting ChromaDB store at {chroma_dir}")
                shutil.rmtree(chroma_dir)
            if db_file.exists():
                logger.info(f"Deleting SQLite file at {db_file}")
                db_file.unlink()
        else:
            logger.info(f"Persona directory {persona_dir} does not exist. Creating it.")
            persona_dir.mkdir(parents=True, exist_ok=True)
    else:
        if not persona_dir.exists():
            persona_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing SQLite database at {db_file}...")
    try:
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            for key, val in TABLES.items():
                if isinstance(val, str):
                    logger.info(f"Creating table: {key}")
                    cursor.execute(val)
                elif isinstance(val, list):
                    for index_sql in val:
                        logger.info(f"Applying index for {key}")
                        cursor.execute(index_sql)
            conn.commit()
        logger.info(f"Successfully initialized SQLite database for persona '{persona}'.")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")
        return

    logger.info(f"Database initialization for persona '{persona}' complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Initialize or rebuild a persona database.')
    parser.add_argument('persona', type=str, help='The persona to initialize (e.g., default, dnd).')
    parser.add_argument('--wipe', action='store_true', help='Wipe existing database and vector store before initializing.')
    
    args = parser.parse_args()
    initialize_database(args.persona, args.wipe)
