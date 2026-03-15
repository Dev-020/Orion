# System Utilities (`system_utils/`)

Scripts and modules for maintenance, backup, and health checks.

## 1. Backup System (`backup_db.py`)
**Critical Component**.
-   **Trigger**: Runs on Startup, Shutdown, and Schedule (every 15m).
-   **Logic**:
    -   Checks if `databases/` has changed (using Hash).
    -   If changed, creates a ZIP archive in `backups/`.
    -   **Gate**: Only allows one backup every 12 hours *unless* forced manually.

## 2. Data Sync & Embedding (`sync_data.py`, `sync_docs.py`, `embed_document.py`)
-   **`sync_data.py`**: Used for migrating data between versions or syncing `instructions/` to the database.
-   **`sync_docs.py`**: Synchronizes instructions and campaign documents from Google Drive to local Markdown files. Supports persona-specific manifests.
-   **`embed_document.py`**: The "Intelligent Sync" engine. It parses Markdown files by header hierarchy, generates unique breadcrumb-aware IDs, and upserts them into ChromaDB. Features local duplicate detection and content-hash ID generation.

## 3. Persona Management (`initialize_database.py`, `refresh_semantic_memory.py`)
-   **`initialize_database.py`**: Central utility for creating or wiping persona databases. Defines the master SQLite schema with robust constraints and indexes.
-   **`refresh_semantic_memory.py`**: Surgical sync utility that rebuilds the Vector DB from SQLite core tables (memory, profiles, rulings) without disturbing external data like 5eTools.

## 4. Diagnostics (`run_startup_diagnostics.py`)
-   Checks if API keys are valid.
-   Checks if Internet is reachable.
-   Verifies database integrity.
-   Ran by `server.py` on startup to "Fail Fast" if configuration is broken.

## 4. TTS (`orion_tts.py`)
-   Text-to-Speech wrapper.
-   Can use local engines (like Piper) or Cloud APIs.
-   Output: Generates Audio bytes sent to Frontend/TUI.
