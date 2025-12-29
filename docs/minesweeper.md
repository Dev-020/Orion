# Minesweeper Implementation Documentation

## Overview
This document details the implementation of the Minesweeper feature (Phase 1) in the Orion codebase. The feature is a full-stack implementation involving a Python backend for game logic/state and a React frontend for the UI, communicating via WebSockets.

## 1. Backend Implementation

The backend logic is primarily located in:
- `backends/minesweeper/logic.py`
- `backends/server.py` (WebSocket Endpoint)

### Core Logic (`minesweeper/logic.py`)
*   **`MinesweeperGame` Class**: 
    *   Manages the state of a single game instance (grid, revealed cells, flags, mines).
    *   Handles move validation (`reveal`, `toggle_flag`).
    *   Checks win/loss conditions.
    *   Generates the client-facing payload (hiding unrevealed mine locations).
*   **`GameManager` Class**: 
    *   A Singleton class responsible for managing active game sessions.
    *   Maps `user_id` (or session ID) to `MinesweeperGame` instances.
    *   Ensures persistence: When a user reconnects, `get_game(id)` returns their existing game instance.

### WebSocket Endpoint (`server.py`)
*   **Route**: `/ws/game`
*   **Authentication**: 
    *   Accepts a `?token=` query parameter.
    *   Uses `AuthManager` to verify the JWT.
    *   If valid, uses the User ID as the session key. If invalid/missing, falls back to an anonymous session ID (non-persistent across reloads).
*   **Handling**:
    *   Located directly in `server.py` to avoid router/middleware conflicts.
    *   On Connect: Checks for an existing game in `GameManager`. If found, sends `game_start` with the current state.
    *   Loop: Listens for JSON commands (`new_game`, `reveal`, `flag`) and responds with updates.

## 2. Frontend Implementation

The frontend is built with React and located in:
- `frontends/web/src/pages/MinesweeperPage.jsx`
- `frontends/web/src/components/Minesweeper/`

### Page Logic (`MinesweeperPage.jsx`)
*   **WebSocket Connection**: Establishes a connection to `/ws/game` on mount.
*   **State Management**:
    *   `grid`: 2D array representing the board.
    *   `gameState`: 'pending', 'playing', 'won', 'lost'.
    *   `socket`: The active WebSocket instance.
*   **Persistence Handling**: 
    *   Does **not** auto-create a new game on connect.
    *   Waits for a `game_start` message from the server (indicating a restored session).
    *   If no session is restored, the `Board` component displays a "Start New Game" prompt.

### Components
*   **`Board.jsx`**: Renders the game grid. Handles Left Click (Reveal) and Right Click (Flag).
*   **`Controls.jsx`**: Displays timer, mine count, difficulty selector, and "New Game" button.
*   **`Board.jsx`**: Includes valid visual states for Numbers, Mines, Flags, and "Glassmorphism" styling.

## 3. API Protocol (WebSocket)

Communication involves JSON payloads sent over the WebSocket.

### Client -> Server commands
*   **New Game**: `{"type": "new_game", "difficulty": "easy" | "medium" | "hard"}`
*   **Reveal Cell**: `{"type": "reveal", "x": 2, "y": 5}`
*   **Toggle Flag**: `{"type": "flag", "x": 2, "y": 5}`

### Server -> Client responses
*   **Game Start** (Sent on connect or new game):
    ```json
    {
      "type": "game_start", 
      "payload": {
        "grid": [...], 
        "state": "playing", 
        "mines_remaining": 10, 
        "time_elapsed": 0 
      }
    }
    ```
*   **Game Update** (Sent after moves):
    ```json
    {
      "type": "game_update", 
      "payload": {
        "state": "playing",
        "updates": [{"x": 2, "y": 5, "value": 3}], // Cells changed
        "flag_update": {"x": 2, "y": 5, "flagged": true}, // If flag toggled
        "mines_remaining": 9
      }
    }
    ```
*   **Error**: `{"type": "error", "message": "..."}`
