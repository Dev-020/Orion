
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

    async def connect(self):
        """Establishes the WebSocket connection."""
        url = f"{self.base_url}/ws/game"
        if self.token:
            url += f"?token={self.token}"
            
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
            # Merge updates into local state (simplified)
            # In a real app we'd deep merge, but for now just replacing what we can
            updates = payload.get("updates", [])
            
            # Note: We don't have the full grid here to update individual cells easily 
            # without a grid object. This SDK just exposes the raw update event.
            if self.on_update: self.on_update(payload)
            
        elif msg_type == "error":
            logger.error(f"Server Error: {data.get('message')}")

    async def new_game(self, difficulty: str = "medium"):
        await self._send({"type": "new_game", "difficulty": difficulty})

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
