# Minesweeper Implementation Documentation

## 1. Overview
The Minesweeper module in Orion is a robust, full-stack implementation of the classic game, enhanced with real-time multiplayer capabilities and an autonomous AI agent ("Orion Bot"). It uses a **Client-Server** architecture over **WebSockets** to ensure secure, authoritative game logic while delivering a responsive, modern "Glassmorphism" UI on the frontend.

## 2. Architecture

### Backend (`backends/minesweeper/`)
The backend logic is modularized for scalability and stability:

- **`logic.py`**:
    - **`MinesweeperGame`**: The core game logic class. Handles board representation (1D/2D mapping), mine generation, recursive flood-fill, and win/loss conditions. It supports multiple modes (`classic`, `flags`).
    - **`GameManager`**: A centralized Singleton that manages active game sessions in memory. It handles:
        - `active_games`: Mapping users to games for quick lookup.
        - `games_by_id`: Registry of all active game lobbies.
        - `cleanup_stale_games`: Garbage collection for abandoned sessions.

- **`routes.py`**:
    - The WebSocket Controller. Handles connection lifecycle, authentication, and message routing.
    - **Connection Management**: Maps persistent `user_ids` (from JWT) to active WebSocket connections, enabling seamless reconnection.
    - **Bot Orchestration**: Manages the spawning and termination of Bot subprocesses.

- **`orion_minesweeper_core.py`**:
    - The standalone AI Agent. Runs as a separate process to ensure isolation.
    - Uses a Hybrid Solver (CSP + Probability) to play the game autonomously.

### Frontend (`frontends/web/src/pages/MinesweeperPage.jsx`)
The React frontend acts as the view layer, synchronizing state with the server:

- **Lobby System**: A dedicated UI (`LobbyControls`) for creating Solo or Multiplayer lobbies.
- **Draft Mode (Lazy Creation)**: In Solo mode, the grid acts as a "Draft". The server session is only created upon the **first move**, optimizing resource usage.
- **Persistence**: The UI automatically reconnects and restores the game state if the browser is refreshed, thanks to persistent User IDs.

## 3. Game Modes

### Classic (Solo)
- **Goal**: Reveal all safe cells without hitting a mine.
- **Rules**: Standard Minesweeper rules.
- **Features**: 
    - "First Click Safe" guarantee.
    - Draft Mode start.

### Flags (Multiplayer)
- **Goal**: Find more mines than your opponent.
- **Mechanics**:
    - **Competitive**: Players take turns or play simultaneously (configurable).
    - **Scoring**: Revealing a mine (or flagging correctly) grants a point.
    - **Victory**: The player with the highest score when all mines are found wins.

## 4. Orion Bot (The "Hunter")
The Orion Bot is a sophisticated AI agent designed to play against humans or test the system.

- **Strategy ("Hunter")**: 
    - Unlike standard solvers that avoid mines, the Hunter **actively seeks mines** in Flags mode to score points.
    - It uses Constraint Satisfaction Problems (CSP) to identify 100% certain mines and reveals them immediately.
- **Lifecycle**:
    - **Summoning**: Can be summoned into a Lobby by the host via `summon_bot`.
    - **Process**: Runs as a detached subprocess.
    - **Termination**: 
        - Automatically terminates if the Game Host leaves.
        - Can be **Kicked** via the UI, which forcibly kills the subprocess.

## 5. Connection & Safety Features
- **Graceful Termination**: When a Host leaves a multiplayer game:
    - **Bots** are forcibly disconnected to ensure process cleanup.
    - **Humans** receive a `game_terminated` signal, resetting their UI to the lobby *without* triggering a "Connection Error".
- **Delayed Disconnect**: The server uses a `delayed_disconnect` helper to ensure final termination messages are delivered before the socket is closed.

## 6. API Protocol (WebSocket)
All communication is JSON-based.

| Action | Direction | Payload Structure | Description |
| :--- | :--- | :--- | :--- |
| **New Game** | Client → Server | `{"type": "new_game", "mode": "classic", "first_move": {x,y}}` | Starts a new game. Supports "First Move" for lazy creation. |
| **Join Game** | Client → Server | `{"type": "join_game", "game_id": "..."}` | Joins an existing multiplayer lobby. |
| **Summon Bot** | Client → Server | `{"type": "summon_bot", "game_id": "..."}` | Spawns an AI bot in the lobby. |
| **Kick Player** | Client → Server | `{"type": "kick_player", "target_id": "..."}` | Removes a player (Bot) from the game. |
| **Leave Game** | Client → Server | `{"type": "leave_game", "game_id": "..."}` | Host destroys game; Client leaves lobby. |
| **Game Terminated** | Server → Client | `{"type": "game_terminated", "message": "..."}` | Signals clients to return to lobby (Host left). |
| **Game Update** | Server → Client | `{"type": "game_update", "payload": {...}}` | Broadcasts grid changes, scores, and turn info. |
