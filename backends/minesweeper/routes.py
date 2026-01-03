
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional, Dict, List
import json
import logging
import os
import asyncio


# Absolute imports
try:
    from minesweeper.logic import GameManager
except ImportError:
    GameManager = None
    logger.error("Could not import GameManager in routes.py")

# Note: We do NOT need to import AuthManager here anymore, as we use the one from app.state

# Setup Logger
logger = logging.getLogger("server") 

router = APIRouter()

# Initialize Managers safely
game_manager = GameManager() if GameManager else None

# Connection Manager for Broadcasting
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def broadcast_to_game(self, game, message: dict):
        """Sends a message to all players in the game."""
        if not game: return
        
        for player_id in game.players:
            ws = self.active_connections.get(player_id)
            if ws:
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.error(f"Broadcast error to {player_id}: {e}")

    async def force_disconnect(self, user_id: str):
        """Forcefully disconnects a user (Kick)."""
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.close(code=1000, reason="Kicked by host")
            except Exception as e:
                logger.error(f"Error closing socket for {user_id}: {e}")
            # Ensure removal
            if user_id in self.active_connections:
                del self.active_connections[user_id]

async def delayed_disconnect(manager: ConnectionManager, user_id: str):
    """Helper to disconnect after a brief delay."""
    await asyncio.sleep(0.5)
    await manager.force_disconnect(user_id)

manager = ConnectionManager()

@router.websocket("/ws/game")
async def game_websocket(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket.accept()
    
    # Access shared AuthManager from Server
    auth_manager = getattr(websocket.app.state, "auth_manager", None)
    
    # 1. Authenticate
    if not token:
        token = websocket.query_params.get("token")
        
    explicit_username = websocket.query_params.get("username")

    user_id = str(id(websocket)) # Default to session ID if no auth
    username = "Anonymous"
    
    if token and auth_manager:
        user = auth_manager.verify_token(token)
        if user:
            user_id = user['user_id']
            username = user['username']
            logger.info(f"Minesweeper connected: {username} ({user_id})")
        else:
             logger.warning("Invalid token for Minesweeper connection")
    
    # Allow override from query param (for Bots or Debug) if explicit
    if explicit_username:
        username = explicit_username
        # If token was invalid but username provided, we trust it for "Anonymous/Bot" context?
        # Yes, Minesweeper logic allows anonymous play.
    
    session_id = user_id 
    
    # Register Connection
    await manager.connect(session_id, websocket)
    
    # 2. Check for existing game (Persistence)
    existing_game = game_manager.get_game(session_id)
    if existing_game:
        logger.info(f"Restoring game for {username}")
        await websocket.send_json({
            "type": "game_start", 
            "payload": existing_game.get_full_state_for_client()
        })
    
    try:
        while True:
            data = await websocket.receive_text()
            # logger.info(f"Minesweeper received: {data}") 
            
            try:
                message = json.loads(data)
                action = message.get("type")
                
                if action == "new_game":
                    logger.info("Processing new_game...")
                    difficulty = message.get("difficulty", "medium")
                    mode = message.get("mode", "classic")
                    invite_ids = message.get("invite_ids", []) # List of user_ids to invite/join
                    first_move = message.get("first_move") # Optional {x, y}
                    
                    players = [session_id] + invite_ids
                    
                    # Create the Game
                    game = game_manager.create_game(session_id, username, difficulty, mode=mode, player_ids=players)
                    logger.info(f"Game created: {game.game_id} (Mode: {mode}, Players: {len(players)})")
                    
                    # Handle Lazy Creation First Move
                    if first_move:
                        fx, fy = first_move.get("x"), first_move.get("y")
                        logger.info(f"Executing First Move at {fx}, {fy}")
                        # Execute reveal locally (no broadcast yet, we will broadcast full state after)
                        game.reveal(fx, fy, player_id=session_id)
                    
                    # Notify ALL players
                    # Since we revealed *before* this, the get_full_state_for_client() will include the revealed cells!
                    await manager.broadcast_to_game(game, {
                        "type": "game_start", 
                        "payload": game.get_full_state_for_client()
                    })
                    logger.info("Game start payload broadcasted.")
                    
                elif action == "join_game":
                    game_id = message.get("game_id")
                    logger.info(f"Processing join_game: {game_id} by {session_id}")
                    
                    game = game_manager.join_game(game_id, session_id, username)
                    
                    if game:
                        logger.info(f"User {session_id} joined game {game_id}. Broadcasting update...")
                        # Notify ALL players (including joiner) so everyone sees the new player count
                        await manager.broadcast_to_game(game, {
                            "type": "game_start", 
                            "payload": game.get_full_state_for_client()
                        })
                    else:
                        await websocket.send_json({"type": "error", "message": "Game not found"})

                elif action == "reveal":
                    game = game_manager.get_game(session_id)
                    if game:
                        x, y = message.get("x"), message.get("y")
                        # Pass session_id for Turn Validation
                        result = game.reveal(x, y, player_id=session_id)
                        
                        if result.get("error"):
                             await websocket.send_json({"type": "error", "message": result["error"]})
                        else:
                            # BROADCAST UPDATE
                            await manager.broadcast_to_game(game, {
                                "type": "game_update",
                                "payload": result
                            })

                elif action == "flag":
                    game = game_manager.get_game(session_id)
                    if game:
                        x, y = message.get("x"), message.get("y")
                        result = game.toggle_flag(x, y)
                        
                        if result.get("error"):
                             await websocket.send_json({"type": "error", "message": result["error"]})
                        else:
                            # BROADCAST UPDATE
                            await manager.broadcast_to_game(game, {
                                "type": "game_update",
                                "payload": result
                            })

                elif action == "summon_bot":
                    game_id = message.get("game_id")
                    logger.info(f"Summoning Bot for game: {game_id}")
                    
                    # Ensure game exists
                    game = game_manager.games_by_id.get(game_id)
                    if not game:
                        await websocket.send_json({"type": "error", "message": "Game not found"})
                    else:
                        # Launch Bot Process
                        import subprocess
                        import sys
                        
                        # Calculate paths relative to backend root
                        current_dir = os.path.dirname(os.path.abspath(__file__)) # backends/minesweeper
                        backend_root = os.path.dirname(current_dir) # backends
                        bot_script = os.path.join(backend_root, "orion_minesweeper_core.py")
                        
                        # Generate Bot Name (Robustly)
                        existing_bots = [p for p in game.player_names.values() if "Orion Bot" in p]
                        import re
                        bot_ids = []
                        for name in existing_bots:
                            match = re.search(r"Orion Bot (\d+)", name)
                            if match:
                                bot_ids.append(int(match.group(1)))
                        
                        next_id = 1
                        if bot_ids:
                            next_id = max(bot_ids) + 1
                        
                        bot_name = f"Orion Bot {next_id}"
                        
                        cmd = [sys.executable, bot_script, "--join_game_id", game_id, "--strategy", "hunter", "--username", bot_name, "--games", "999"]
                        
                        # Run in background (detachedish)
                        try:
                            subprocess.Popen(cmd)
                            logger.info(f"Bot process launched: {cmd}")
                            await websocket.send_json({"type": "bot_summoned", "message": "The Hunter Bot has entered the lobby."})
                        except Exception as e:
                            logger.error(f"Failed to summon bot: {e}")
                            await websocket.send_json({"type": "error", "message": f"Failed to summon bot: {e}"})

                elif action == "leave_game":
                    game_id = message.get("game_id")
                    logger.info(f"User {session_id} leaving game {game_id}")
                    # Remove the game entirely (clean up session)
                    removed_game = game_manager.remove_game(game_id=game_id)
                    
                    if removed_game:
                        # Force disconnect all other players (e.g. Bots) to ensure they exit
                        # The current user (session_id) is already disconnecting via UI, 
                        # but we can ensure cleanup for everyone.
                        for pid in removed_game.players:
                            if pid != session_id: # Optional: Don't kill self if we want to stay open? 
                                                  # But 'leave_game' usually implies moving to lobby.
                                                  # Actually, force_disconnect closes the socket, so it's fine.
                                logger.info(f"Closing connection for {pid} due to game termination.")
                                try:
                                    # Try to notify the user before cutting the connection
                                    ws_peer = manager.active_connections.get(pid)
                                    if ws_peer:
                                        await ws_peer.send_json({
                                            "type": "game_terminated",
                                            "message": "The host has left the game. Returning to lobby."
                                        })
                                except Exception as e:
                                    logger.error(f"Failed to send termination message to {pid}: {e}")
                                    
                                # Logic Check: Only disconnect if it's a BOT.
                                # Humans should stay connected (but returned to lobby).
                                # Bots must be disconnected to terminate their process.
                                player_name = removed_game.player_names.get(pid, "")
                                if "Bot" in player_name: 
                                    # Give client a moment to process the message before closing
                                    asyncio.create_task(delayed_disconnect(manager, pid))
                                else:
                                    # Human: Do not disconnect. They are just returned to lobby via the message.
                                    pass

                    # No need to broadcast, game is gone. 
                    # If multiplayer, we might want to just remove THIS player, but for now we destroy the session as per plan (Restart).

                elif action == "restart_game":
                    game_id = message.get("game_id")
                    new_difficulty = message.get("difficulty")
                    logger.info(f"Restarting game {game_id} with difficulty {new_difficulty}")
                    
                    game = game_manager.games_by_id.get(game_id)
                    if game:
                        game.reset(difficulty=new_difficulty)
                        await manager.broadcast_to_game(game, {
                            "type": "game_start",
                            "payload": game.get_full_state_for_client()
                        })

                elif action == "kick_player":
                    target_id = message.get("target_id")
                    logger.info(f"Kick request: {session_id} kicking {target_id}")
                    # Validate: Only allow kicking Bots for now (or improve auth later)
                    # For V1: We allow any player to kick a BOT.
                    # We should check if target_id corresponds to a bot.
                    
                    game = game_manager.get_game(session_id)
                    if game and target_id in game.players:
                        target_name = game.player_names.get(target_id, "")
                        if "Bot" in target_name: # Simple security check: Only kick Bots
                             logger.info(f"Kicking Bot: {target_name}")
                             
                             # 1. Remove from Game
                             game_manager.remove_player_from_game(game.game_id, target_id)
                             
                             # 2. Force Disconnect (Terminates Bot Process)
                             await manager.force_disconnect(target_id)
                             
                             # 3. Broadcast Update
                             await manager.broadcast_to_game(game, {
                                "type": "game_start", 
                                "payload": game.get_full_state_for_client()
                             })
                        else:
                             await websocket.send_json({"type": "error", "message": "Only Bots can be kicked."})
                    else:
                        await websocket.send_json({"type": "error", "message": "Player not found or no game."})

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Game Processing Error: {e}")
                
    except WebSocketDisconnect:
        # Note: We do NOT remove the game on disconnect if we want persistence!
        # game_manager.remove_game(session_id) 
        
        # If it's a BOT, we MUST remove it so it disappears from scoreboard
        if "Bot" in username:
             logger.info(f"Bot {username} disconnected. Removing from game.")
             game = game_manager.get_game(session_id)
             if game:
                 game_manager.remove_player_from_game(game.game_id, session_id)
                 # Broadcast update to remaining players
                 asyncio.create_task(manager.broadcast_to_game(game, {
                    "type": "game_start",
                    "payload": game.get_full_state_for_client()
                 }))

        manager.disconnect(session_id)
        logger.info(f"Minesweeper session {username} disconnected")
