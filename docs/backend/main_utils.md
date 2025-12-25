# Main Utilities (`main_utils/`)

This directory contains the shared libraries that power the Core.

## 1. Authentication Manager (`auth_manager.py`)
-   **Database**: Uses `databases/users.db` (SQLite).
-   **Hashing**: Uses `bcrypt` for secure password storage.
-   **Token**: Uses `PyJWT` to generate Bearer tokens.
-   **Profile**: Stores user settings (Avatar URL, Display Name) in a JSON column or separate table.

## 2. Configuration (`config.py`)
-   **Purpose**: Single source of truth for Environment Variables.
-   **Loading**: Loads `.env` file using `python-dotenv`.
-   **Variables**:
    -   `GEMINI_API_KEY`: Google API Key.
    -   `BACKEND_TYPE`: `google` or `ollama`.
    -   `HOST`, `PORT`: Server settings.

## 3. Tool Definitions (`main_functions.py`)
**The Toolbox**. This file contains every function the AI can call.
-   **Structure**: Each function is decorated with metadata (name, description, parameters).
-   **Examples**:
    -   `get_weather(city)`
    -   `google_search(query)`
    -   `read_file_content(path)`
-   **Loader**: `OrionCore` inspects this module to build the "Tools" list sent to Gemini/Ollama.

## 4. Logger (`orion_logger.py`)
-   Standardizes logging formats across the app.
-   Ensures logs go to `data/logs/` and `stdout` (for TUI capture).
