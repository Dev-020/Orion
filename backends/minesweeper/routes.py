
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional
import json
import logging
import os


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

@router.websocket("/ws/game")
async def game_websocket(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket.accept()
    
    # Access shared AuthManager from Server
    auth_manager = getattr(websocket.app.state, "auth_manager", None)
    
    # 1. Authenticate
    if not token:
        token = websocket.query_params.get("token")

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
            # logger.info(f"Minesweeper received: {data}") 
            
            try:
                message = json.loads(data)
                action = message.get("type")
                
                if action == "new_game":
                    logger.info("Processing new_game...")
                    difficulty = message.get("difficulty", "medium")
                    game = game_manager.create_game(session_id, difficulty)
                    logger.info(f"Game created: {game.game_id}. Sending payload...")
                    
                    await websocket.send_json({
                        "type": "game_start", 
                        "payload": game.get_full_state_for_client()
                    })
                    logger.info("Game start payload key sent.")

                elif action == "reveal":
                    game = game_manager.get_game(session_id)
                    if game:
                        x, y = message.get("x"), message.get("y")
                        result = game.reveal(x, y)
                        await websocket.send_json({
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
                            await websocket.send_json({
                                "type": "game_update",
                                "payload": result
                            })

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Game Processing Error: {e}")
                
    except WebSocketDisconnect:
        # Note: We do NOT remove the game on disconnect if we want persistence!
        # game_manager.remove_game(session_id) 
        # Only remove if anonymous? maybe. For now keep it to allow refresh.
        logger.info(f"Minesweeper session {username} disconnected")
