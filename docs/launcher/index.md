# Launcher Dashboard

The **Launcher** (`launcher.py`) is the control center of Orion. It is a Terminal User Interface (TUI) built using `Textual`.

## Why a TUI?
Instead of managing 3-4 separate terminal windows (Backend, Frontend, Ngrok, Logs), the Launcher aggregates everything into one screen.

## Features

### 1. Process Management
The launcher uses `launcher_app/process_manager.py` to spawn subprocesses:
-   **Backend**: `uvicorn backends.server:app` (Port 8000).
-   **Frontend**: `npm run dev` (Port 5173).
-   **Ngrok**: `ngrok http --url=...` (Tunnel).

> [!NOTE]
> The launcher monitors these processes. If one crashes, it captures the exit code and can restart it.

### 2. Log Aggregation
It captures `stdout` and `stderr` from all subprocesses and routes them to the "Log View" widget.
-   **Color Coding**: Backend logs are green, Frontend logs are cyan, Errors are red.
-   **Scrolling**: Auto-scrolls to the latest message.

### 3. Ngrok Management
The launcher parses the ngrok output to find the public URL (e.g., `https://funny-pigeon.ngrok-free.app`). It displays this prominently so you can copy it for the Discord Bot or Mobile access.

## Controls
-   `q`: Quit the application (shuts down all subprocesses).
-   `r`: Restart the Backend server (useful for dev).
-   `l`: Clear logs.
