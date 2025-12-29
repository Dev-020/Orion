
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Optional
import json
import logging
import os
from .logic import GameManager
from ..main_utils.auth_manager import AuthManager

# Setup Logger
logger = logging.getLogger("Minesweeper")

router = APIRouter()
game_manager = GameManager()

# Load Auth Manager (Same secret as server.py)
auth_manager = AuthManager(secret_key=os.getenv("JWT_SECRET", "super-secret-key"))

@router.websocket("/ws/game")
async def game_websocket(websocket: WebSocket):
    await websocket.accept()
    
    # 1. Authenticate
    token = websocket.query_params.get("token")
    user_id = str(id(websocket)) # Default to session ID if no auth
    username = "Anonymous"
    
    if token:
        user = auth_manager.verify_token(token)
        if user:
            user_id = user['user_id']
            username = user['username']
            logger.info(f"Minesweeper connected: {username} ({user_id})")
        else:
             logger.warning("Invalid token for Minesweeper connection")
             # We could close, or allow anon play. 
             # For persistence, we need valid auth. 
             # Let's allow anon play effectively (no persistence across refresh)
    
    session_id = user_id 
    
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
            try:
                message = json.loads(data)
                action = message.get("type")
                
                if action == "new_game":
                    # For new game, we might overwrite existing one
                    difficulty = message.get("difficulty", "medium")
                    game = game_manager.create_game(session_id, difficulty)
                    await websocket.send_json({
                        "type": "game_start", 
                        "payload": game.get_full_state_for_client()
                    })

                    
                elif action == "reveal":
                    game = game_manager.get_game(session_id)
                    if game:
                        x, y = message.get("x"), message.get("y")
                        result = game.reveal(x, y)
                        
                        # logic.py now returns the full payload structure we need
                        # We just need to wrap it in our WS message type
                        response = {
                            "type": "game_update",
                            "payload": result
                        }
                        await websocket.send_json(response)
                
                elif action == "flag":
                    game = game_manager.get_game(session_id)
                    if game:
                        x, y = message.get("x"), message.get("y")
                        result = game.toggle_flag(x, y)
                        
                        # If error (limit reached)
                        if result.get("error"):
                             await websocket.send_json({"type": "error", "message": result["error"]})
                        else:
                            response = {
                                "type": "game_update", # Use generic update for stats sync
                                "payload": result
                            }
                            await websocket.send_json(response)

            except json.JSONDecodeError:
                await websocket.send_text("Invalid JSON")
            except Exception as e:
                logger.error(f"Game Error: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        game_manager.remove_game(session_id)
        logger.info(f"Minesweeper session {session_id} disconnected")
