
import asyncio
import websockets
import json
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger("MinesweeperClient")

class MinesweeperClient:
    """
    A Python SDK for the Minesweeper Game Server.
    Allows scripts/bots to play the game via WebSockets.
    """
    def __init__(self, base_url: str = "ws://127.0.0.1:8000", token: str = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.ws = None
        self.game_state: Dict[str, Any] = {}
        self.on_update: Optional[Callable[[Dict], None]] = None
        self._running = False

    async def connect(self, username: str = None):
        """Establishes the WebSocket connection."""
        from urllib.parse import quote
        
        url = f"{self.base_url}/ws/game"
        
        # Build query params
        params = []
        if self.token:
            params.append(f"token={quote(self.token)}")
        if username:
            params.append(f"username={quote(username)}")
            
        if params:
            url += "?" + "&".join(params)
            
        logger.info(f"Connecting to {url}...")
        try:
            self.ws = await websockets.connect(url)
            self._running = True
            logger.info("Connected!")
            
            # Start listening loop in background
            asyncio.create_task(self._listen())
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    async def _listen(self):
        """Internal loop to process incoming messages."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                self._handle_message(data)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Connection closed.")
            self._running = False
        except Exception as e:
            logger.error(f"Listener error: {e}")

    def _handle_message(self, data: Dict):
        msg_type = data.get("type")
        
        if msg_type == "game_start":
            self.game_state = data.get("payload", {})
            logger.info("Game Started/Restored")
            if self.on_update: self.on_update(self.game_state)
            
        elif msg_type == "game_update":
            payload = data.get("payload", {})
            
            # Update local grid state
            if self.game_state and "grid" in self.game_state:
                updates = payload.get("updates", [])
                for u in updates:
                    ux, uy, val = u.get("x"), u.get("y"), u.get("value")
                    if 0 <= uy < len(self.game_state["grid"]) and 0 <= ux < len(self.game_state["grid"][0]):
                        self.game_state["grid"][uy][ux] = val
                
                # Update mines/flags count if present
                if "mines_remaining" in payload:
                    self.game_state["mines_remaining"] = payload["mines_remaining"]
                if "state" in payload:
                    self.game_state["state"] = payload["state"]
                    
                # Multiplayer Fields
                if "scores" in payload:
                    self.game_state["scores"] = payload["scores"]
                if "current_turn" in payload:
                    self.game_state["current_turn"] = payload["current_turn"]
                if "mode" in payload:
                    self.game_state["mode"] = payload["mode"]
                    
                if "flag_update" in payload:
                    f = payload["flag_update"]
                    fx, fy, is_flagged = f.get("x"), f.get("y"), f.get("flagged")
                    if 0 <= fy < len(self.game_state["grid"]) and 0 <= fx < len(self.game_state["grid"][0]):
                        # If flagged -> "F", if unflagged -> None (Hidden)
                        self.game_state["grid"][fy][fx] = "F" if is_flagged else None

            if self.on_update: self.on_update(self.game_state)
            
        elif msg_type == "error":
            logger.error(f"Server Error: {data.get('message')}")

    async def new_game(self, difficulty: str = "medium", mode: str = "classic", invite_ids: list = None):
        payload = {
            "type": "new_game", 
            "difficulty": difficulty,
            "mode": mode
        }
        if invite_ids:
            payload["invite_ids"] = invite_ids
            
        await self._send(payload)

    async def join_game(self, game_id: str):
        await self._send({"type": "join_game", "game_id": game_id})

    async def reveal(self, x: int, y: int):
        await self._send({"type": "reveal", "x": x, "y": y})

    async def flag(self, x: int, y: int):
        await self._send({"type": "flag", "x": x, "y": y})
        
    async def _send(self, data: Dict):
        if self.ws and self._running:
            await self.ws.send(json.dumps(data))
        else:
            logger.warning("Cannot send, not connected.")

    async def close(self):
        if self.ws:
            await self.ws.close()
