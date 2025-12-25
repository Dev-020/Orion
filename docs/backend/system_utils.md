# System Utilities (`system_utils/`)

Scripts and modules for maintenance, backup, and health checks.

## 1. Backup System (`backup_db.py`)
**Critical Component**.
-   **Trigger**: Runs on Startup, Shutdown, and Schedule (every 15m).
-   **Logic**:
    -   Checks if `databases/` has changed (using Hash).
    -   If changed, creates a ZIP archive in `backups/`.
    -   **Gate**: Only allows one backup every 12 hours *unless* forced manually.

## 2. Data Sync (`sync_data.py`)
-   Used for migrating data between versions or syncing `instructions/` to the database.

## 3. Diagnostics (`run_startup_diagnostics.py`)
-   Checks if API keys are valid.
-   Checks if Internet is reachable.
-   Verifies database integrity.
-   Ran by `server.py` on startup to "Fail Fast" if configuration is broken.

## 4. TTS (`orion_tts.py`)
-   Text-to-Speech wrapper.
-   Can use local engines (like Piper) or Cloud APIs.
-   Output: Generates Audio bytes sent to Frontend/TUI.
