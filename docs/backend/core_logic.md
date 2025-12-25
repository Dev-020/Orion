# Core Logic

This section explains the heart of Orion: the Server, the Brain (Core), and the Client.

## 1. The Server (`backends/server.py`)
**Type**: FastAPI Application.

The server is the entry point for all external interaction. It initializes the `OrionCore` on startup using a `lifespan` manager.

### Key Responsibilities
-   **Initialization**: Loads `AuthenticationManager`, `BackupSystem`, and `OrionCore` (Lite or Full).
-   **Static Files**: Serves Avatar images from `avatars/`.
-   **Endpoints**:
    -   `POST /process_prompt`: The main chat loop.
    -   `WS /ws`: WebSocket for real-time chat (used by TUI/Legacy clients).
    -   `POST /upload_file`: Handles file uploads to the analyzed area.

## 2. The Brain (`backends/orion_core.py`)
**Type**: Logic Class (`OrionCore`).

This file contains the business logic for the AI assistant. It does **not** handle HTTP; it simply processes inputs and returns iterators (streams).

### Key Features
-   **Session Management**: Keeps track of `chat_object` instances for each session ID.
-   **Prompt Construction**: Merges "System Instructions", "User Instructions", "Attached Files", and "Conversation History" into a single payload for the Model.
-   **Tool Calling**: When the model requests a function call (e.g., `get_weather`), Core executes it from `main_utils.main_functions` and feeds the result back.

### The "Lite" Core (`backends/orion_core_lite.py`)
A stripped-down version designed for **Ollama**.
-   It uses the OpenAI-compatible API client to talk to local models (Llama 3, Mistral, etc.).
-   It mimics the API of the full Core so they can be hot-swapped in `server.py`.

## 3. The Client (`backends/orion_client.py`)
**Type**: SDK Wrapper.

**Who uses this?**
-   The Discord Bot (`frontends/bot.py`)
-   The Desktop GUI (`frontends/gui.py`)

**What does it do?**
It mimics the `OrionCore` class methods (like `process_prompt`), but instead of running logic, it performs HTTP calls to `http://localhost:8000`. This allows Python apps to run separate from the server.
