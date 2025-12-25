# Backend API & Protocols

## Connection Info
-   **Default Port**: `8000`
-   **Host**: `127.0.0.1` (Localhost)
-   **Base URL**: `http://127.0.0.1:8000`

## Core Endpoints

### 1. Chat Processing (`POST /process_prompt`)
This is the main endpoint for sending messages to the AI.

**Request Payload:**
```json
{
  "prompt": "Hello world",
  "session_id": "user_123",
  "user_id": "user_123",
  "username": "User",
  "files": [], 
  "stream": true
}
```

**Response:**
Returns a **Server-Sent Events (SSE)** style stream (MIME: `application/x-ndjson`). Each line is a JSON object representing a token or metadata chunk.

### 2. File Upload (`POST /upload_file`)
Handles uploading images, documents, or text files for analysis.

**Form Data:**
-   `file`: The binary file content.
-   `display_name`: Filename.
-   `mime_type`: e.g., `image/png`.

### 3. WebSocket (`WS /ws`)
Used for real-time bidirectional communication if needed, though `/process_prompt` is currently preferred for stability in the React app.

## Authentication
Authentication is handled via `Bearer` tokens.
-   **Header**: `Authorization: Bearer <token>`
-   **Manager**: `backends/main_utils/auth_manager.py` manages the SQLite user database.
