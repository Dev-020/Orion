# Minesweeper Implementation Documentation

## 1. Overview
This feature implements a full-stack Minesweeper game within Orion. It uses a robust Client-Server architecture over WebSockets, ensuring game logic is secure and persistent on the backend while providing a responsive "Glassmorphism" UI on the frontend.

## 2. Backend Architecture

### Core Components
The backend is modularized to ensure separation of concerns:

- **`minesweeper/logic.py`**:
    - **`MinesweeperGame`**: Pure Python class handling the board state, mine generation, recursive flood-fill for revealing zeros, and win/loss rules.
    - **`GameManager`**: A singleton class managing active game sessions in memory (RAM). It maps `session_id` to `MinesweeperGame` instances.
- **`minesweeper/routes.py`**:
    - Defines the `APIRouter` for the WebSocket endpoint.
    - **Dependency Injection**: Accesses `app.state.auth_manager` (initialized in `server.py`) to share the same authentication context (Database & Secret Keys) as the main server.
- **`server.py`**:
    - Mounts the `minesweeper_router` to the main FastAPI app.
    - Manages the global `AuthManager` lifecycle.

### Connection & Authentication flows
1.  **Connection**: Client connects to `/ws/game?token=<jwt>`.
2.  **Auth Verification**: The router uses the shared `AuthManager` to verify the JWT.
    - **Success**: The persistent `user_id` is used as the session key. This allows a user to refresh the page and reconnect to the *exact same game*.
    - **Failure/No Token**: Falls back to an `Anonymous` session tied to the WebSocket ID (lost on disconnect).
3.  **Restoration**: Upon connection, the server checks `GameManager` for an existing game for that user. If found, it immediately sends a `game_start` payload to restore the board.

### SDK (`minesweeper_client.py`)
A standalone Python SDK provided for "headless" interactions. This is used for automated testing and will be the foundation for the AI Bot agent.

```python
from minesweeper_client import MinesweeperClient

# Example: Headless interaction
client = MinesweeperClient("ws://localhost:8000")
await client.connect(token="...")
await client.new_game("medium")
await client.reveal(5, 5)
```

## 3. Frontend Architecture
Built with React (Vite) and located in `frontends/web/src/`.

- **`MinesweeperPage.jsx`**: 
    - The main controller.
    - Handles WebSocket connection lifecycle (connect, disconnect, reconnect).
    - Manages local state (`grid`, `gameState`, `timers`).
    - **Smart Persistence**: Does *not* automatically start a new game on load. It waits for the server to dictate if there is an existing game to resume.
- **`Board.jsx`**: 
    - Renders the 2D grid.
    - Handles user inputs (Left Click = Reveal, Right Click = Flag).
    - Styling: Uses Tailwind CSS for a dark, modern look with distinct colors for numbers.
- **`Controls.jsx`**: 
    - Difficulty selector (Easy 9x9, Medium 16x16, Hard 16x30).
    - Game status indicators (Timer, Mines Left).

## 4. API Protocol (WebSocket)
All communication happens via JSON payloads.

| Action | Direction | Payload Structure | Description |
| :--- | :--- | :--- | :--- |
| **New Game** | Client → Server | `{"type": "new_game", "difficulty": "medium"}` | Request to destroy current game (if any) and start fresh. |
| **Reveal** | Client → Server | `{"type": "reveal", "x": 5, "y": 3}` | Reveal a specific cell. Triggers flood-fill if 0. |
| **Flag** | Client → Server | `{"type": "flag", "x": 5, "y": 3}` | Toggle flag on a covered cell. |
| **Game Start** | Server → Client | `{"type": "game_start", "payload": { "grid": [...], "state": "playing", ... }}` | Sent on reconnection (restore) or after New Game. |
| **Update** | Server → Client | `{"type": "game_update", "payload": { "grid": [...], "state": "won" }}` | Sent after a move causes a change. |
| **Error** | Server → Client | `{"type": "error", "message": "Invalid Move"}` | Sent if validation fails. |

## 5. Future Roadmap (Phase 2)

### Phase 2.1: Minesweeper Bot (`orion_minesweeper_core.py`)
Development of an autonomous AI agent capable of solving Minesweeper games.
- **Algorithms**: Hybrid usage of **CSP (Constraint Satisfaction)** for logical deduction and **Probabilistic Models** for making the safest optimal guess in ambiguous situations.
- **Architecture**: Will be built as a standalone service utilizing the `MinesweeperClient` SDK.

### Phase 2.2: Multiplayer
- **Lobbies**: Upgrading `GameManager` to support "Rooms" where multiple users can join.
- **Race Mode**: Real-time 1v1 battles where two players solve identical boards. First to clear wins.
